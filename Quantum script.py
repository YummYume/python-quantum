import sys
import json
import webbrowser
import time
import plotly.figure_factory as ff
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import traceback
from threading import Timer
from copy import deepcopy
import dash
from dash import html
from dash import dcc
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
from dash_bootstrap_templates import load_figure_template

# App constants
app = dash.Dash(
    external_stylesheets = [dbc.themes.SOLAR]
)
load_figure_template("solar")
port = 8050

# Constants
QUANTUM = 5
CONTEXT_CHANGE_DURATION = 2
UNIT = "u."
PROCESSES = [
    {
        "processId": "p1",
        "duration": 30,
        "startTime": 0
    },
    {
        "processId": "p2",
        "duration": 30,
        "startTime": 0
    },
]

# ProcessList Class
class ProcessList:
    def __init__(self, id, processes, quantum, contextChangeDuration, unit) -> None:
        self.id = id
        self.processes = processes
        self.quantum = quantum
        self.contextChangeDuration = contextChangeDuration
        self.unit = unit
        self.data = {
            "time": 0,
            "contextChangeTime": 0,
            "idleTime": 0,
            "ganttChart": [],
            "averageWaitingTimeBeforeStart": 0,
            "averageWaitingTime": 0,
            "averageLoadingTime": 0,
            "averageJourneyTime": 0,
            "runTime": 0
        }

    # Run processes
    def runProcesses(self):
        print("Running processes of process list %s..." % self.id)
        firstEntry = True
        idleTasks = []
        time = self.data["time"]
        contextChangeTime = self.data["contextChangeTime"]
        idleTime = self.data["idleTime"]
        ganttChart = self.data["ganttChart"]

        # If at least one process is not finished
        while processesRunning(self.processes):
            # Cannot run any process
            if processesAwaiting(self.processes, time):
                timeBeforeEntry = time
                time += 1
                idleTime +=1
                idleTasks.append(dict(
                    Task = "Idle Time",
                    Start = timeBeforeEntry,
                    Finish = time,
                    Resource = "Idle Time",
                    Description = "No process to run."
                ))
            # Can run at least one process
            else:
                for process in self.processes:
                    timeBeforeEntry = time
                    # Process can run
                    if process.finished == False and process.startTime <= time:
                        # First process to run (no context change)
                        if firstEntry:
                            firstEntry = False
                            processTime = process.progress(self.processes, self.quantum, time, self.unit, 0)
                            time += processTime

                            ganttChart.append(dict(
                                Task = "Process %s" % process.id,
                                Start = timeBeforeEntry,
                                Finish = time,
                                Resource = "Process",
                                Description = "Lasted %s%s, from %s%s to %s%s. %s%s remaining to complete." % (self.unit, processTime, self.unit, timeBeforeEntry, self.unit, time, self.unit, process.duration)
                            ))
                        # Process is running
                        else:
                            processTime = process.progress(self.processes, self.quantum, time, self.unit, self.contextChangeDuration)
                            time += self.contextChangeDuration + processTime
                            contextChangeTime += self.contextChangeDuration

                            ganttChart.append(dict(
                                Task = "Process %s" % process.id,
                                Start = timeBeforeEntry,
                                Finish = timeBeforeEntry + self.contextChangeDuration,
                                Resource = "Context Change",
                                Description = "Context change to process %s." % process.id
                            ))
                            ganttChart.append(dict(
                                Task = "Process %s" % process.id,
                                Start = timeBeforeEntry + self.contextChangeDuration,
                                Finish = time,
                                Resource = "Process",
                                Description = "Lasted %s%s, from %s%s to %s%s. %s%s remaining to complete." % (self.unit, processTime, self.unit, timeBeforeEntry + self.contextChangeDuration, self.unit, time, self.unit, process.duration)
                            ))

        # Create Gantt chart now for later
        for idleTask in idleTasks:
            ganttChart.append(idleTask)

        # Update self data
        data = {
            "time": time,
            "contextChangeTime": contextChangeTime,
            "idleTime": idleTime,
            "ganttChart": ganttChart
        }

        self.data.update(data)
        self.setAverageWaitingTimeBeforeStart()
        self.setAverageWaitingTime()
        self.setAverageLoadingTime()
        self.setAverageJourneyTime()
        self.setRunTime()

        print("Finished process list %s at %s%s." % (self.id, self.unit, self.data["time"]))
        print("Average waiting before start for processes is %s%s." % (self.unit, self.data["averageWaitingTimeBeforeStart"]))
        print("Average waiting for processes is %s%s." % (self.unit, self.data["averageWaitingTime"]))
        print("Average loading for processes is %s%s." % (self.unit, self.data["averageLoadingTime"]))
        print("Average journey for processes is %s%s." % (self.unit, self.data["averageJourneyTime"]))
        print("Total idling of %s%s.\n" % (self.unit, self.data["idleTime"]))

    # Sets the average waiting time before start (TMA)
    def setAverageWaitingTimeBeforeStart(self):
        awtbs = 0

        for process in self.processes:
            awtbs += process.waitTimeBeforeStart

        data = {
            "averageWaitingTimeBeforeStart": round(awtbs/len(self.processes))
        }

        self.data.update(data)

    # Sets the average waiting time
    def setAverageWaitingTime(self):
        awt = 0

        for process in self.processes:
            awt += process.waitTime

        data = {
            "averageWaitingTime": round(awt/len(self.processes))
        }

        self.data.update(data)

    # Sets the average loading time
    def setAverageLoadingTime(self):
        data = {
            "averageLoadingTime": round(self.data["time"]/len(self.processes))
        }

        self.data.update(data)

    # Sets the average journey time
    def setAverageJourneyTime(self):
        ajt = 0

        for process in self.processes:
            ajt += process.journeyTime

        data = {
            "averageJourneyTime": round(ajt/len(self.processes))
        }

        self.data.update(data)

    # Sets the total run time
    def setRunTime(self):
        data = {
            "runTime": self.data["time"] - (self.data["contextChangeTime"] + self.data["idleTime"])
        }

        self.data.update(data)

    def getGraphs(self):
        ganttColors = {"Process": 'rgb(0, 255, 100)', "Context Change": 'rgb(105, 105, 105)', "Idle Time": 'rgb(255, 140, 0)'}
        pieLabels = ['Run time', 'Context change time']
        pieValues = [self.data["runTime"], self.data["contextChangeTime"]]
        if self.data["idleTime"] > 0:
            pieLabels.append('Idle time')
            pieValues.append(self.data["idleTime"])
        pieColors = ['rgb(0, 255, 100)', 'rgb(105, 105, 105)', 'rgb(255, 140, 0)']

        cardContent = [
            dbc.CardHeader("Data for process list %s" % self.id),
            dbc.CardBody(
                [
                    html.P(
                        "Number of processes : %s" % len(self.processes),
                        className = "card-text"
                    ),
                    html.P(
                        "Quantum : %s%s" % (self.unit, self.quantum),
                        className = "card-text"
                    ),
                    html.P(
                        "Context change duration : %s%s" % (self.unit, self.contextChangeDuration),
                        className = "card-text"
                    ),
                    html.P(
                        "Average waiting time before start : %s%s" % (self.unit, self.data["averageWaitingTimeBeforeStart"]),
                        className = "card-text"
                    ),
                    html.P(
                        "Average waiting time : %s%s" % (self.unit, self.data["averageWaitingTime"]),
                        className = "card-text"
                    ),
                    html.P(
                        "Average loading time : %s%s" % (self.unit, self.data["averageLoadingTime"]),
                        className = "card-text"
                    ),
                    html.P(
                        "Average journey time : %s%s" % (self.unit, self.data["averageJourneyTime"]),
                        className = "card-text"
                    ),
                ]
            ),
        ]
        gantt = ff.create_gantt(self.data["ganttChart"], colors = ganttColors, index_col = 'Resource', show_colorbar = True, group_tasks = True, height = (16 * len(self.processes)) + 16, title = "Chart of Processes")
        gantt.update_xaxes(type = 'linear')
        pieChart = go.Figure(data = [go.Pie(labels = pieLabels, values = pieValues, marker_colors = pieColors, title = "PieChart of Runtimes")])

        return {
            "cardContent": cardContent,
            "gantt": gantt,
            "pieChart": pieChart
        }

# Process class
class Process:
    # Builder
    def __init__(self, id, duration, startTime) -> None:
        self.id = id
        self.duration = max(duration, 1)
        self.startTime = max(startTime, 0)
        self.endTime = None
        self.started = False
        self.finished = False
        self.runTime = 0                # Time spent running
        self.waitTimeBeforeStart = 0    # Waiting time before first entry
        self.waitTime = 0               # Waiting time as a whole
        self.journeyTime = 0            # Time from first entry to finish

    # Run the process (returns running time)
    def progress(self, processes = None, quantum = QUANTUM, currentTime = None, unit = UNIT, contextChangeDuration = CONTEXT_CHANGE_DURATION):
        # Process is not finished
        if self.finished == False:
            # Process can run
            if currentTime is not None and self.startTime <= (currentTime + contextChangeDuration):
                time = currentTime + contextChangeDuration

                # Only one process can run
                if processes is not None and singleProcessRun(processes, time):
                    i = 0
                    while singleProcessRun(processes, time + i):
                        if self.duration > 0:
                            self.duration -= 1
                            self.runTime += 1

                            if self.started == False:
                                self.started = True
                                self.waitTimeBeforeStart = time

                            if self.duration <= 0:
                                self.endTime = time + i
                                self.duration = 0
                                self.finished = True
                                self.waitTime = (time - self.startTime) - self.runTime
                                self.journeyTime = self.endTime - self.waitTimeBeforeStart
                                print("Process \"%s\" finished at %s%s." % (self.id, unit, self.endTime))
                                
                                return i
                            
                            i += 1

                    return i
                # Multiple processes can run
                else:
                    for i in range(1, quantum + 1):
                        if self.duration > 0:
                            self.duration -= 1
                            self.runTime += 1

                            if self.started == False:
                                self.started = True
                                self.waitTimeBeforeStart = time

                            if self.duration <= 0:
                                self.endTime = time + i
                                self.duration = 0
                                self.finished = True
                                self.waitTime = (time - self.startTime) - self.runTime
                                self.journeyTime = self.endTime - self.waitTimeBeforeStart
                                print("Process \"%s\" finished at %s%s." % (self.id, unit, self.endTime))

                                return i
            else:
                return 0
            
        else:
            return 0

        return quantum

# Returns a list of Processes objects
def toProcesses(processes):
    finalProcesses = []
    i = 0

    for process in processes:
        i += 1
        id = "p%s" % i
        duration = 1
        startTime = 0

        if "processId" in process:
            id = process["processId"]

        if "duration" in process:
            duration = process["duration"]

        if "startTime" in process:
            startTime = process["startTime"]

        finalProcesses.append(Process(id, duration, startTime))

    return finalProcesses

# Returns True if at least one process is not finished
def processesRunning(processes):
    for process in processes:
        if process.finished == False:
            return True

    return False

# Returns True if only processes not finished cannot run yet (idle time)
def processesAwaiting(processes, currentTime):
    for process in processes:
        if process.finished == False and process.startTime <= currentTime:
            return False

    return True

# Returns True if only one process is running
def singleProcessRun(processes, currentTime):
    numProcessAvailable = 0

    for process in processes:
        if process.finished == False and process.startTime <= currentTime:
            numProcessAvailable += 1

    if numProcessAvailable == 1:
        return True

    return False

# To open browser
def open_browser():
	webbrowser.open_new("http://localhost:{}".format(port))

# Generate a list of quantums based on the quantum given
def generateQuantums(quantum = QUANTUM):
    quantums = []
    minusQuantums = []
    plusQuantums = []

    for i in range(1, 6):
        newQuantum = max(1, quantum - (i * 5))
        if newQuantum not in minusQuantums:
            minusQuantums.append(newQuantum)

    for i in range(1, 6):
        newQuantum = max(1, quantum + (i * 5))
        if newQuantum not in plusQuantums:
            plusQuantums.append(newQuantum)

    quantums.extend(list(reversed(minusQuantums)))
    quantums.append(quantum)
    mainIndex = len(quantums) - 1
    quantums.extend(plusQuantums)

    return {
        "quantums": quantums,
        "mainIndex": mainIndex
    }

# Updates the graphs depending on the quantum selected
@app.callback(
    Output('gantt-graph', 'figure'),
    Output('pie-chart', 'figure'),
    Output('info-card', 'children'),
    Input('quantum', 'value')
)
def updateQuantumGraphs(processListId):
    if isinstance(processListId, int):
        processListSelect = next((processList for processList in processLists if processList.id == processListId), None)
        if processListSelect is not None:
            graphData = processListSelect.getGraphs()

            return graphData["gantt"], graphData["pieChart"], graphData["cardContent"]

        raise PreventUpdate

    raise PreventUpdate

# Adds a quantum and updates the global graphs
@app.callback(
    Output('alert-success', 'is_open'),
    Output('alert-danger', 'is_open'),
    Output('quantum-id', 'data'),
    Output('quantum', 'options'),
    Output('quantums-text', 'children'),
    Output('linechart-1-graph', 'figure'),
    Output('linechart-1-graph', 'className'),
    Output('linechart-2-graph', 'figure'),
    Output('linechart-2-graph', 'className'),
    Output('linechart-3-graph', 'figure'),
    Output('linechart-3-graph', 'className'),
    Output('linechart-4-graph', 'figure'),
    Output('linechart-4-graph', 'className'),
    Input('add-quantum-button', 'n_clicks'),
    State('quantum-input', 'value'),
    State('quantum-id', 'data')
)
def addQuantum(n, newQuantum, quantumId):
    if n is not None:
        if isinstance(newQuantum, str):
            try:
                newQuantum = int(newQuantum)
            except:
                print("Value %s cannot be converted to int." % newQuantum)

        if isinstance(newQuantum, int) and newQuantum > 0 and newQuantum < 101 and not any(processList.quantum == newQuantum for processList in processLists):
            newProcessList = ProcessList(quantumId, deepcopy(processes), newQuantum, contextChangeDuration, unit)
            newProcessList.runProcesses()
            processLists.append(newProcessList)
            processLists.sort(key = lambda x: x.quantum, reverse = False)

            dropdownOptions = []
            for processList in processLists:
                dropdownOptions.append({
                    'label': "%s%s" % (unit, processList.quantum),
                    'value': processList.id
                })

            quantumsText = "Quantums : %s" % (", ".join(unit + str(processList.quantum) for processList in processLists))

            lineChartsData["x"]["averageWaitingTimeBeforeStart"].append(newQuantum)
            lineChartsData["x"]["averageWaitingTime"].append(newQuantum)
            lineChartsData["x"]["averageLoadingTime"].append(newQuantum)
            lineChartsData["x"]["averageJourneyTime"].append(newQuantum)

            lineChartsData["y"]["averageWaitingTimeBeforeStart"].append(newProcessList.data["averageWaitingTimeBeforeStart"])
            lineChartsData["y"]["averageWaitingTime"].append(newProcessList.data["averageWaitingTime"])
            lineChartsData["y"]["averageLoadingTime"].append(newProcessList.data["averageLoadingTime"])
            lineChartsData["y"]["averageJourneyTime"].append(newProcessList.data["averageJourneyTime"])

            df = pd.DataFrame(dict(
                x = lineChartsData["x"]["averageWaitingTimeBeforeStart"],
                y = lineChartsData["y"]["averageWaitingTimeBeforeStart"]
            ))
            df = df.sort_values(by = "x")
            averageWaitingTimeBeforeStartLineChart = px.line(df, x = "x", y = "y", title = "Average waiting time before start", markers = True)
            averageWaitingTimeBeforeStartLineChart.update_layout(xaxis_title = "Quantum", yaxis_title = timeLabel)

            df = pd.DataFrame(dict(
                x = lineChartsData["x"]["averageWaitingTime"],
                y = lineChartsData["y"]["averageWaitingTime"]
            ))
            df = df.sort_values(by = "x")
            averageWaitingTimeLineChart = px.line(df, x = "x", y = "y", title = "Average waiting time", markers = True)
            averageWaitingTimeLineChart.update_layout(xaxis_title = "Quantum", yaxis_title = timeLabel)

            df = pd.DataFrame(dict(
                x = lineChartsData["x"]["averageLoadingTime"],
                y = lineChartsData["y"]["averageLoadingTime"]
            ))
            df = df.sort_values(by = "x")
            averageLoadingTimeLineChart = px.line(df, x = "x", y = "y", title = "Average loading time", markers = True)
            averageLoadingTimeLineChart.update_layout(xaxis_title = "Quantum", yaxis_title = timeLabel)

            df = pd.DataFrame(dict(
                x = lineChartsData["x"]["averageJourneyTime"],
                y = lineChartsData["y"]["averageJourneyTime"]
            ))
            df = df.sort_values(by = "x")
            averageJourneyTimeLineChart = px.line(df, x = "x", y = "y", title = "Average journey time", markers = True)
            averageJourneyTimeLineChart.update_layout(xaxis_title = "Quantum", yaxis_title = timeLabel)

            quantumId += 1

            return True, False, quantumId, dropdownOptions, quantumsText, averageWaitingTimeBeforeStartLineChart, 'd-block', averageWaitingTimeLineChart, 'd-block', averageLoadingTimeLineChart, 'd-block', averageJourneyTimeLineChart, 'd-block'

        return False, True, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

    raise PreventUpdate

# Main
if __name__ == "__main__":
    processes = PROCESSES
    quantum = QUANTUM
    contextChangeDuration = CONTEXT_CHANGE_DURATION
    unit = UNIT
    fileName = input("\nPath to Json file (processVariableStart.json) : ")
    if fileName == "":
        fileName = "processVariableStart.json"
        
        # Read json file and get values (otherwise get constants)
        try:
            print("\nReading %s file..." % fileName)

            with open(fileName, encoding='utf-8-sig') as jsonFile:
                data = json.load(jsonFile)

                if "quantumDuration" in data and isinstance(data["quantumDuration"], int) and data["quantumDuration"] > 0:
                    quantum = int(data["quantumDuration"])
                    print("quantumDuration loaded.")

                if "contextSwapDuration" in data and isinstance(data["contextSwapDuration"], int) and data["contextSwapDuration"] > 0:
                    contextChangeDuration = int(data["contextSwapDuration"])
                    print("contextSwapDuration loaded.")

                if "unit" in data and isinstance(data["unit"], str):
                    unit = data["unit"]
                    print("unit loaded.")

                if "processList" in data and isinstance(data["processList"], list) and len(data["processList"]) > 0:
                    processes = toProcesses(data["processList"])
                    print("processList loaded.")

        except Exception:
            print("An error occured while reading file %s." % fileName)
            print("Error : %s" % traceback.format_exc())
            input("Press any key to continue...")
            sys.exit()

    # Run process lists and get data
    try:
        quantums = [quantum]
        processLists = []
        mainId = 0
        mainIndex = 0
        quantumId = 0
        timeLabel = "Time (%s)" % unit
        lineChartsData = {
            "x": {
                "averageWaitingTimeBeforeStart": [],
                "averageWaitingTime": [],
                "averageLoadingTime": [],
                "averageJourneyTime": []
            },
            "y" : {
                "averageWaitingTimeBeforeStart": [],
                "averageWaitingTime": [],
                "averageLoadingTime": [],
                "averageJourneyTime": []
            }
        }
        multipleQuantums = input("\nGenerate multiple quantums? (y/n) : ")

        if multipleQuantums == "" or multipleQuantums == "y" or multipleQuantums == "yes":
            quantumData = generateQuantums(quantum)
            quantums = quantumData["quantums"]
            mainIndex = quantumData["mainIndex"]

        for generateQuantum in quantums:
            processLists.append(ProcessList(quantumId, deepcopy(processes), generateQuantum, contextChangeDuration, unit))
            if quantumId == mainIndex:
                mainId = quantumId

            quantumId += 1

        for processList in processLists:
            processList.runProcesses()
            currentQuantum = processList.quantum

            # Prepare the lineCharts
            lineChartsData["x"]["averageWaitingTimeBeforeStart"].append(currentQuantum)
            lineChartsData["x"]["averageWaitingTime"].append(currentQuantum)
            lineChartsData["x"]["averageLoadingTime"].append(currentQuantum)
            lineChartsData["x"]["averageJourneyTime"].append(currentQuantum)

            lineChartsData["y"]["averageWaitingTimeBeforeStart"].append(processList.data["averageWaitingTimeBeforeStart"])
            lineChartsData["y"]["averageWaitingTime"].append(processList.data["averageWaitingTime"])
            lineChartsData["y"]["averageLoadingTime"].append(processList.data["averageLoadingTime"])
            lineChartsData["y"]["averageJourneyTime"].append(processList.data["averageJourneyTime"])
    
    except Exception:
        print("An error occured...")
        print("Error : %s" % traceback.format_exc())
        input("Press any key to continue...")
        sys.exit()

    # Create graphs and Dash app, then open in browser
    try:
        showGraph = input("Show graphs? (y/n) : ")

        if showGraph == "" or showGraph == "y" or showGraph == "yes":
            processListGraph = next((processList for processList in processLists if processList.id == mainId), None)
            graphData = processListGraph.getGraphs()
            dropdownOptions = []
            
            for processList in processLists:
                dropdownOptions.append({
                    'label': "%s%s" % (unit, processList.quantum),
                    'value': processList.id
                })

            htmlView = [
                dcc.Store(
                    id = 'quantum-id',
                    data = quantumId
                ),
                html.H1(
                    children = 'Graphs of Processes',
                    className = 'my-2',
                    style = {
                        'textAlign': 'center',
                        'color': '#B0C4DE'
                    }
                ),
                html.Div(
                    children = 'Results of the processes running using the round-robin scheduling.',
                    className = 'my-2',
                    style = {
                        'textAlign': 'center',
                        'color': '#B0C4DE'
                    }
                ),
                dbc.Alert(
                    "The quantum has been added.",
                    id = "alert-success",
                    color = "success",
                    is_open = False,
                    duration = 4000,
                    dismissable = True,
                    style = {
                        'margin': '20px'
                    }
                ),
                dbc.Alert(
                    "Please enter a valid quantum (1-100) that does not already exist.",
                    id = "alert-danger",
                    color = "danger",
                    is_open = False,
                    duration = 4000,
                    dismissable = True,
                    style = {
                        'margin': '20px'
                    }
                ),
                dbc.Row(
                    [
                        html.Div([
                            dbc.Col(
                                html.P(
                                    "Quantum :",
                                    style = {
                                        'paddingLeft': '20px'
                                    }
                                ),
                            ),
                            dbc.Col(
                                dcc.Dropdown(
                                    id = 'quantum',
                                    options = dropdownOptions,
                                    value = processListGraph.id,
                                    style = {
                                        'paddingLeft': '20px',
                                        'minWidth': '150px'
                                    }
                                ),
                            )
                        ]),
                        html.Div([
                            dbc.Col(
                                html.P(
                                    "Add a quantum (1-100) :"
                                ),
                            ),
                            dbc.Input(
                                id = 'quantum-input',
                                placeholder = 'Enter a quantum...',
                                className = 'd-inline-block',
                                type = 'number',
                                style = {
                                    'width': '65%'
                                }
                            ),
                            dbc.Button(
                                id = 'add-quantum-button',
                                color = 'primary',
                                children = 'Add',
                                className = 'd-inline-block',
                                style = {
                                    'marginLeft': '5px',
                                    'marginBottom': '5px'
                                }
                            )
                        ])
                    ],
                    className = 'mt-2 mb-4 mx-0',
                ),
                dcc.Graph(
                    id = 'gantt-graph',
                    figure = graphData["gantt"],
                    className = 'mb-5'
                ),
                html.H2(
                    'PieChart & Data',
                    className = 'my-2',
                    style = {
                        'textAlign': 'center',
                        'color': '#B0C4DE'
                    }
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            dcc.Graph(
                                id = 'pie-chart',
                                figure = graphData["pieChart"]
                            ),
                        width = 12, sm = 6),
                        dbc.Col(
                            dbc.Card(
                                graphData["cardContent"],
                                id = 'info-card',
                                color = "info",
                                outline = True,
                                style = {
                                    'marginTop': '50px',
                                },
                            ),
                        width = 12, sm = 6, md = 5, lg = 4, xl = 3),
                    ],
                    justify = "around",
                    className = 'my-5 mx-0'
                ),
                html.H2(
                    'Global Data with LineCharts',
                    className = 'my-2',
                    style = {
                        'textAlign': 'center',
                        'color': '#B0C4DE'
                    }
                ),
                html.Div(
                    id = 'quantums-text',
                    children = "Quantums : %s" % (", ".join(unit + str(processList.quantum) for processList in processLists)),
                    className = 'mb-5',
                    style = {
                        'textAlign': 'center',
                        'color': '#B0C4DE'
                    }
                )
            ]

            displayGraph1 = 'd-none'
            displayGraph2 = 'd-none'
            displayGraph3 = 'd-none'
            displayGraph4 = 'd-none'

            if len(lineChartsData["x"]["averageWaitingTimeBeforeStart"]) > 1 and len(lineChartsData["y"]["averageWaitingTimeBeforeStart"]) > 1:
                displayGraph1 = 'd-block'

            if len(lineChartsData["x"]["averageWaitingTime"]) > 1 and len(lineChartsData["y"]["averageWaitingTime"]) > 1:
                displayGraph2 = 'd-block'

            if len(lineChartsData["x"]["averageLoadingTime"]) > 1 and len(lineChartsData["y"]["averageLoadingTime"]) > 1:
                displayGraph3 = 'd-block'

            if len(lineChartsData["x"]["averageJourneyTime"]) > 1 and len(lineChartsData["y"]["averageJourneyTime"]) > 1:
                displayGraph4 = 'd-block'

            df = pd.DataFrame(dict(
                x = lineChartsData["x"]["averageWaitingTimeBeforeStart"],
                y = lineChartsData["y"]["averageWaitingTimeBeforeStart"]
            ))
            df = df.sort_values(by = "x")
            averageWaitingTimeBeforeStartLineChart = px.line(df, x = "x", y = "y", title = "Average waiting time before start", markers = True)
            averageWaitingTimeBeforeStartLineChart.update_layout(xaxis_title = "Quantum", yaxis_title = timeLabel)

            htmlView.append(
                dcc.Graph(
                    id = 'linechart-1-graph',
                    figure = averageWaitingTimeBeforeStartLineChart,
                    className = displayGraph1
                ),
            )

            df = pd.DataFrame(dict(
                x = lineChartsData["x"]["averageWaitingTime"],
                y = lineChartsData["y"]["averageWaitingTime"]
            ))
            df = df.sort_values(by = "x")
            averageWaitingTimeLineChart = px.line(df, x = "x", y = "y", title = "Average waiting time", markers = True)
            averageWaitingTimeLineChart.update_layout(xaxis_title = "Quantum", yaxis_title = timeLabel)

            htmlView.append(
                dcc.Graph(
                    id = 'linechart-2-graph',
                    figure = averageWaitingTimeLineChart,
                    className = displayGraph2
                ),
            )

            df = pd.DataFrame(dict(
                x = lineChartsData["x"]["averageLoadingTime"],
                y = lineChartsData["y"]["averageLoadingTime"]
            ))
            df = df.sort_values(by = "x")
            averageLoadingTimeLineChart = px.line(df, x = "x", y = "y", title = "Average loading time", markers = True)
            averageLoadingTimeLineChart.update_layout(xaxis_title = "Quantum", yaxis_title = timeLabel)

            htmlView.append(
                dcc.Graph(
                    id = 'linechart-3-graph',
                    figure = averageLoadingTimeLineChart,
                    className = displayGraph3
                ),
            )

            df = pd.DataFrame(dict(
                x = lineChartsData["x"]["averageJourneyTime"],
                y = lineChartsData["y"]["averageJourneyTime"]
            ))
            df = df.sort_values(by = "x")
            averageJourneyTimeLineChart = px.line(df, x = "x", y = "y", title = "Average journey time", markers = True)
            averageJourneyTimeLineChart.update_layout(xaxis_title = "Quantum", yaxis_title = timeLabel)

            htmlView.append(
                dcc.Graph(
                    id = 'linechart-4-graph',
                    figure = averageJourneyTimeLineChart,
                    className = displayGraph4
                ),
            )
            
            app.layout = html.Div(children = htmlView)
            Timer(1, open_browser).start();
            app.run_server(debug = True, port = port, use_reloader = False)

    except Exception:
        print("An error occured...")
        print("Error : %s" % traceback.format_exc())
        input("Press any key to continue...")
        sys.exit()