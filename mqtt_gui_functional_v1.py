import os
import sys
import json
import csv
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
import pyqtgraph as pg
import numpy as np
import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS
import threading
from datetime import datetime
import time


class MQTTThread(QThread):                          # allows running MQTT in the background without freezing the GUI.
    message_received = pyqtSignal(str, str)         # emits the received - topic, payload
    connection_status = pyqtSignal(bool, str)       #  emits the status  - connected, message, 


    def __init__(self, host, port):
        super().__init__()
        self.host = host        # MQTT Host details
        self.port = port        # MQTT Port details
        self.mqtt_client = None # Initialized to 'None' but will hold the MQTT client object.
        self.running = True     # a flag to keep the thread running.


    def run(self):
        self.mqtt_client = mqtt.Client()                # Creates a MQTT client instance.                
        self.mqtt_client.on_connect = self.on_connect   # Assign the 'on_connect' function
        self.mqtt_client.on_message = self.on_message   # Assign the 'on_message' function

        try:
            self.mqtt_client.connect(self.host, int(self.port))     # try to connect to the MQTT Broker
            self.mqtt_client.loop_start()                           # Keep the 'loop on' to run the MQTT in the background 
            while self.running:
                self.msleep(100)                                    # Prevent high CPU usage, after no response
        except Exception as e:
            self.connection_status.emit(False, str(e))              # If not connected, emit the error message


    def stop(self):
        self.running = False                                        # Used for stop the MQTT Server (Exit the GUI)
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()                           # Disconnect the client


    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:                                                                     # if connection is successful with return code = 0
            self.connection_status.emit(True, "Connected")                              # Emits the status Connected
            client.subscribe("#")                                                       # Subscribe to all avaliable topics on connect
        else:
            self.connection_status.emit(False, f"Connection failed with code {rc}")     # if connection is not successfull, emits "Connection failed" with error return code 


    def on_message(self, client, userdata, message):
        self.message_received.emit(message.topic, message.payload.decode())             # Emits the received topic and decoded payload


    def publish(self, topic, payload):
        if self.mqtt_client and self.mqtt_client.is_connected():                        # If connection is done
            self.mqtt_client.publish(topic, payload)                                    # publish a message


    def subscribe(self, topic):
        if self.mqtt_client and self.mqtt_client.is_connected():
            self.mqtt_client.subscribe(topic)                                           # subscribe all the avaliable topics


class CustomDateAxisItem(pg.DateAxisItem):


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setStyle(showValues=True)
        self.enableAutoSIPrefix(False)
        

    def tickStrings(self, values, scale, spacing):
        # Just return the values as is, without time formatting
        return [f"{val/1000:.1f}" for val in values]


class MQTTMonitor(QtWidgets.QMainWindow):                                               # Creates the main window for the application.
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MQTT Environmental Monitor")
        self.resize(1433, 1143)
        
        # Initialize data storage
        self.data_buffer = {f'frame_{i}': {'time': [], 'values': [], 'topic': None} for i in range(1, 7)}   # stores timestamps, values, and assigned topics for 6 frames.
        self.plot_widgets = {}                                                                              # holds references to plot components.
        self.latest_values = {}                                                                             # stores the most recent data.

        # Data storage settings
        self.max_data_hours = 24            # Default to 24 hours
        self.view_hours = 1                 # Default to 1 hour view
        self.auto_save_interval = 3600      # Save every hour
        self.last_save_time = time.time()
        
        # Dynamic topic structure
        self.topic_structure = {}
        self.available_topics = set()
        
        # MQTT Thread
        self.mqtt_thread = None
        self.mqtt_connected = False
        
        # InfluxDB Client setup
        self.influx_client = None
        self.influx_connected = False
        
        # Setup UI
        self.setup_ui()
        
        # Setup timers
        self.update_timer = QtCore.QTimer(self)
        self.update_timer.timeout.connect(self.update_plots)
        self.update_timer.start(1000)                          # Sets up a timer to update plots every second.
        
        self.manual_update_timer = QtCore.QTimer(self)
        self.manual_update_timer.timeout.connect(self.update_manual_values)
        self.manual_update_timer.start(1000)
        
        # Auto-save timer
        self.save_timer = QtCore.QTimer(self)
        self.save_timer.timeout.connect(self.auto_save_data)
        self.save_timer.start(self.auto_save_interval * 1000)
        

    def setup_ui(self):
        self.central_widget = QtWidgets.QWidget()             # Creates a central widget to hold all other widgets
        self.setCentralWidget(self.central_widget)
        
        # Create main layout
        layout = QtWidgets.QVBoxLayout(self.central_widget)   # A vertical layout -- main skeleton
        
        # Create tab widget
        self.tabs = QtWidgets.QTabWidget()                    # A tab widget for different tabs
        layout.addWidget(self.tabs)
        
        # Setup individual tabs
        self.setup_plot_tab()                                 # Plot Monitor Tab
        self.setup_settings_tab()                             # Settings Tab 
        self.setup_manual_tab()                               # Manual Control 

# This function initializes the Plot Monitoring Tab in the GUI, allowing users to visualize MQTT data in real-time. It provides:
# - Controls to select MQTT topics and assign them to different plots.
# - A grid of six plot widgets arranged in a 3x2 layout.
# - Additional features like freezing plots, adjusting the time range, and refreshing topics.


    def setup_plot_tab(self):                       # Initialize the Plot Monitor Tab in the GUI, Controls to select parameter to plot in one of 6 frame arranged in 3x2 layout
        plot_tab = QtWidgets.QWidget()              # A QWidget that will serve as the container for the plotting interface
        layout = QtWidgets.QVBoxLayout(plot_tab)    # Layout to set all main plot widget in vertical alighment
        
        # Controls at the top
        controls = QtWidgets.QHBoxLayout()                                  # Layput for the buttons on the top in horizontal
        
        # Topic selection
        controls.addWidget(QtWidgets.QLabel("Select Topic:"))               # Label : Select Topic
        self.topic_combo = QtWidgets.QComboBox()                            # Combo box to select a topic from the avaliable MQTT Topics
        self.topic_combo.currentTextChanged.connect(self.update_subtopics)  # Calls the 'update_subtopics' function to show available sub topics within the sletected topic
        controls.addWidget(self.topic_combo)
        
        # Subtopic selection
        controls.addWidget(QtWidgets.QLabel("Select Subtopic:"))            # Label : Selct Subtopic
        self.subtopic_combo = QtWidgets.QComboBox()                         # Combo box to select a sub-topic within the selected Topic
        self.subtopic_combo.setEnabled(False)                               # Disable initially, only enable if topic is selected and subtopics are available = dynamical loading
        controls.addWidget(self.subtopic_combo)
        
        # Frame selection
        controls.addWidget(QtWidgets.QLabel("Select Frame:"))               # Label : Select Frame
        self.frame_combo = QtWidgets.QComboBox()                            # Combo box to select frame
        self.frame_combo.addItems([f"Frame {i}" for i in range(1, 7)])      # There are 6 availble frames
        controls.addWidget(self.frame_combo)
        
        # Plot button
        self.plot_button = QtWidgets.QPushButton("Plot")                    # PushButton : Plot
        self.plot_button.clicked.connect(self.start_plotting)               # If topic, subtopic & frame is selected, on clicked, start plot the data, calls 'start_plotting()'
        controls.addWidget(self.plot_button)
        
        # Clear button
        self.clear_button = QtWidgets.QPushButton("Clear")                  # PushButton : Clear
        self.clear_button.clicked.connect(self.clear_plot)                  # Calls 'clear_plot()' to remove plotted data.
        controls.addWidget(self.clear_button)
        
        # Freeze checkbox
        self.freeze_checkbox = QtWidgets.QCheckBox("Freeze Plot")           # CheckBox : Frezze / Unfrezze ; to pause all the plots and analyse them
        self.freeze_checkbox.stateChanged.connect(self.toggle_freeze)       # Calls toggle_freeze() when checked/unchecked.
        controls.addWidget(self.freeze_checkbox)
        
        # Refresh Topics button
        self.refresh_button = QtWidgets.QPushButton("Refresh Topics")       # PushButton : Refresh Topics
        self.refresh_button.clicked.connect(self.refresh_topics)            #  Calls refresh_topics() to reload available topics.
        controls.addWidget(self.refresh_button)
        
        controls.addStretch()
        layout.addLayout(controls)
        
        # Create grid layout for plots
        grid = QtWidgets.QGridLayout()
        
        # Initialize freeze state dictionary
        self.freeze_states = {f'frame_{i}': False for i in range(1, 7)}                                     # Dictionary tracking which plots are frozen.
        self.frozen_data = {f'frame_{i}': {'time': [], 'values': [], 'topic': None} for i in range(1, 7)}   # Stores data in the background when a plot is frozen.
        
        # Create 6 plot widgets in 3x2 grid
        for i in range(6):
            frame = QtWidgets.QGroupBox(f"Frame {i+1}")                 # Creates a QGroupBox titled "Frame 1", "Frame 2", ..., "Frame 6"
            frame_layout = QtWidgets.QVBoxLayout(frame)                 # Assigns a QVBoxLayout to organize elements inside the each frame
            
            # Create plot widget with enhanced visibility
            plot_widget = pg.PlotWidget()                               # A real-time plotting widget.
            plot_widget.setBackground('w')                              # White background for better visibility.
            plot_widget.showGrid(x=True, y=True)                        # Grid enabled for better visualization.
            plot_widget.setLabel('left', 'Value')                       # Y-axis labeled "Value"
            plot_widget.setLabel('bottom', '')                          # X-axis label is Removed, but default it is a time axis always.
            
            # Configure time axis with better formatting
            date_axis = CustomDateAxisItem(orientation='bottom')        # Custom X-axis formats time data.
            plot_widget.setAxisItems({'bottom': date_axis})             # replaces the default X-axis.
            
            # Enable mouse interaction and zooming
            plot_widget.setMouseEnabled(x=True, y=True)                 # Enables zooming and panning
            
            # Configure ViewBox settings
            view_box = plot_widget.getViewBox()                             # Enable ViewBox
            view_box.setMouseMode(view_box.RectMode)                        # Allows zooming.
            view_box.enableAutoRange(axis=view_box.XAxis, enable=True)      # Automatically adjusts axis limits in x-axis.
            view_box.enableAutoRange(axis=view_box.YAxis, enable=True)      # Automatically adjusts axis limits in y-axis 
            view_box.setLimits(xMin=None, xMax=None, yMin=None, yMax=None)  # No default limit
            view_box.disableAutoRange()                                     # Disable auto-range to prevent limit errors, unwanted jumps in axis limits.
            
            # Add antialiasing for smoother lines
            plot_widget.setAntialiasing(True)
            
            # Add time range slider
            time_slider = QtWidgets.QSlider(Qt.Horizontal)                                              # allows adjusting the time range of the plot.
            time_slider.setRange(0, 100)                                                                # Will be updated dynamically (Defines the percentage of data shown)
            time_slider.setValue(100)                                                                   # Show most recent data by default
            time_slider.valueChanged.connect(lambda v, f=f'frame_{i+1}': self.update_time_window(v, f)) # Calls update_time_window() when changed, show plot for the selected time 
            
            frame_layout.addWidget(plot_widget)
            
            # Add slider layout
            slider_layout = QtWidgets.QHBoxLayout()
            slider_layout.addWidget(QtWidgets.QLabel("Time Range:"))
            slider_layout.addWidget(time_slider)
            frame_layout.addLayout(slider_layout)
            
            # Add stats panel : Displays real-time statistics (current, max, min, avg, std deviation).
            stats_layout = QtWidgets.QHBoxLayout()          
            stats = {
                'Current': QtWidgets.QLabel("Current: --"),
                'Max': QtWidgets.QLabel("Max: --"),
                'Min': QtWidgets.QLabel("Min: --"),
                'Avg': QtWidgets.QLabel("Avg: --"),
                'Std': QtWidgets.QLabel("Std: --")
            }
            for label in stats.values():
                stats_layout.addWidget(label)
            frame_layout.addLayout(stats_layout)
            
            # Store references to plots, statistics, and sliders.
            self.plot_widgets[f'frame_{i+1}'] = {
                'plot': plot_widget,
                'stats': stats,
                'curve': None,
                'slider': time_slider
            }
            
            grid.addWidget(frame, i // 2, i % 2)        # Arranges plots in a 3x2 layout (i // 2, i % 2).
        
        layout.addLayout(grid)                          # Adds the grid to the main layout.
        self.tabs.addTab(plot_tab, "Plot Monitor")      # Name the tab "Plot Monitor"
        
        # Initialize subtopics
        self.update_subtopics(self.topic_combo.currentText())   # Updates available subtopics based on the currently selected topic

# This section defines the Settings Tab of the GUI. The tab allows users to:

# - Connect to an MQTT Broker
# - Connect to an InfluxDB database
# - Manage MQTT topics and their hierarchical structure
# - Configure user settings (e.g., name, email, alerts)
# - Manage data storage settings (e.g., format, retention policy)


    def setup_settings_tab(self):
        settings_tab = QtWidgets.QWidget()              # A new tab for settings.
        layout = QtWidgets.QVBoxLayout(settings_tab)    # A vertical layout to arrange elements top-to-bottom
        
        # Left side: Server settings [MQTT Connection Settings, InfluxDB Connection Settings] and MQTT Tree View
        left_layout = QtWidgets.QVBoxLayout()
        
        # MQTT Server settings group
        server_group = QtWidgets.QGroupBox("MQTT Server Settings")      # GroupBox titled "Server Settings."
        server_layout = QtWidgets.QFormLayout()
        
        self.mqtt_host = QtWidgets.QLineEdit("localhost")               # Input field for the MQTT broker address (default: "localhost").
        self.mqtt_port = QtWidgets.QLineEdit("1883")                    # Input field for the MQTT port (default: "1883").
        self.mqtt_status = QtWidgets.QLineEdit("Not Connected")         # Show the connection status, initially "Not Connected"
        self.mqtt_status.setReadOnly(True)                              # Displays connection status (read-only)
        
        # Adds labels and corresponding fields to the settings panel.
        server_layout.addRow("MQTT Host:", self.mqtt_host)
        server_layout.addRow("MQTT Port:", self.mqtt_port)
        server_layout.addRow("Status:", self.mqtt_status)
        
        # MQTT Server Connect button
        self.connect_button = QtWidgets.QPushButton("Connect")          # PushButtion "Connect"
        self.connect_button.clicked.connect(self.connect_mqtt)          # Calls connect_mqtt() when clicked
        server_layout.addRow("", self.connect_button)
        
        server_group.setLayout(server_layout)
        left_layout.addWidget(server_group)
        
        # InfluxDB settings
        influx_group = QtWidgets.QGroupBox("InfluxDB Settings")                     # GroupBox titled "Server Settings."
        influx_layout = QtWidgets.QFormLayout()
        
        self.influx_url = QtWidgets.QLineEdit()                                     # Input for InfluxDB server address
        self.influx_token = QtWidgets.QLineEdit()                                   # Input for authentication token
        self.influx_org = QtWidgets.QLineEdit()                                     # Input for InfluxDB organization
        self.influx_bucket = QtWidgets.QLineEdit()                                  # Input for selecting the storage bucket
        
        influx_layout.addRow("URL:", self.influx_url)
        influx_layout.addRow("Token:", self.influx_token)
        influx_layout.addRow("Organization:", self.influx_org)
        influx_layout.addRow("Bucket:", self.influx_bucket)
        
        # Connect InfluxDB button
        self.influx_connect_button = QtWidgets.QPushButton("Connect to InfluxDB")   # PushButtion : Connect to InfluxDB
        self.influx_connect_button.clicked.connect(self.connect_influxdb)           # Calls connect_influxdb() when clicked.
        influx_layout.addRow("", self.influx_connect_button)
        
        influx_group.setLayout(influx_layout)
        left_layout.addWidget(influx_group)
        
        # Topic Tree View
        tree_group = QtWidgets.QGroupBox("Topic Structure")                         # Creates "Topic Structure" section for displaying MQTT topics
        tree_layout = QtWidgets.QVBoxLayout()
        
        self.topic_tree = QtWidgets.QTreeWidget()
        self.topic_tree.setHeaderLabel("Topics")                                    # A tree view widget for visualizing topic hierarchy
        self.update_topic_tree()                                                    # Loads the latest topics
        
        tree_layout.addWidget(self.topic_tree)
        tree_group.setLayout(tree_layout)
        left_layout.addWidget(tree_group)
        
        # Right side: User settings ,data storage and retention
        right_layout = QtWidgets.QVBoxLayout()
        
        # User settings group
        user_group = QtWidgets.QGroupBox("User Settings")                   # Creates "User Settings" section
        user_layout = QtWidgets.QFormLayout()
        
        self.user_name = QtWidgets.QLineEdit()                              # Input USER name
        self.user_email = QtWidgets.QLineEdit()                             # Input USER Email
        self.email_alerts = QtWidgets.QCheckBox("Enable Email Alerts")      # Check box to enable email allerts
        
        user_layout.addRow("Name:", self.user_name)
        user_layout.addRow("Email:", self.user_email)
        user_layout.addRow("", self.email_alerts)
        
        user_group.setLayout(user_layout)
        right_layout.addWidget(user_group)
        
        # Data storage settings
        storage_group = QtWidgets.QGroupBox("Data Storage")                     # Creates "Data Storage" section
        storage_layout = QtWidgets.QFormLayout()
        
        self.storage_path = QtWidgets.QLineEdit("./data")                       # User specifies the directory
        self.storage_format = QtWidgets.QComboBox()                             # Dropdown to select data format (CSV or JSON)
        self.storage_format.addItems(["CSV", "JSON"])
        
        storage_layout.addRow("Storage Path:", self.storage_path)
        storage_layout.addRow("Format:", self.storage_format)
        
        # Add Data Retention Settings
        retention_group = QtWidgets.QGroupBox("Data Retention Settings")        # Creates "Data Retention Settings" section
        retention_layout = QtWidgets.QFormLayout()
        
        # Maximum data storage time
        self.max_hours_spin = QtWidgets.QSpinBox()
        self.max_hours_spin.setRange(1, 168)                                    # Spin box for setting data retention period (1 hour to 1 week = 168 hrs)
        self.max_hours_spin.setValue(self.max_data_hours)
        self.max_hours_spin.valueChanged.connect(self.update_data_retention)    # Calls update_data_retention() when changed.
        retention_layout.addRow("Store data for (hours):", self.max_hours_spin)
        
        # View window slider
        self.view_hours_slider = QtWidgets.QSlider(Qt.Horizontal)               # Slider to adjust the viewing window of stored data
        self.view_hours_slider.setRange(1, self.max_data_hours)
        self.view_hours_slider.setValue(self.view_hours)
        self.view_hours_slider.valueChanged.connect(self.update_view_window)    # Calls update_view_window() when adjusted
        retention_layout.addRow("View window (hours):", self.view_hours_slider)
        
        # View window display
        self.view_hours_label = QtWidgets.QLabel(f"Current view: {self.view_hours} hour(s)")    # Displays the current time window size
        retention_layout.addRow("", self.view_hours_label)
        
        retention_group.setLayout(retention_layout)
        storage_layout.addRow("", retention_group)
        
        # Save button : Adds data retention options to the UI
        self.save_button = QtWidgets.QPushButton("Save Data")                   # Button to manually save data
        self.save_button.clicked.connect(self.save_data)
        storage_layout.addRow("", self.save_button)
        
        storage_group.setLayout(storage_layout)
        right_layout.addWidget(storage_group)
        
        # Combine layouts
        h_layout = QtWidgets.QHBoxLayout()
        h_layout.addLayout(left_layout)
        h_layout.addLayout(right_layout)
        layout.addLayout(h_layout)
        
        self.tabs.addTab(settings_tab, "Settings")
        

    def update_topic_tree(self):                                    # Provides hierarchical visualization of MQTT topics, Keeps the GUI synchronized with MQTT topics received dynamically
        self.topic_tree.clear()                                     # Clears the existing topic tree before repopulating it with updated topic
        
        def add_items(parent, structure):                           # Recursive Function to Add Topics to Tree
            if isinstance(structure, dict):
                for key, value in structure.items():                # It iterates over self.topic_structure, which stores MQTT topics in a nested dictionary format
                    item = QtWidgets.QTreeWidgetItem([key])         # Creates a QTreeWidgetItem for each topic key.
                    if parent is None:
                        self.topic_tree.addTopLevelItem(item)       # If no topic/subtopics available, show the the items directly
                    else:
                        parent.addChild(item)                       # Adds child topics recursively to maintain a hierarchical tree
                    if value is not None:
                        add_items(item, value)
        
        add_items(None, self.topic_structure)                       # Calls the recursive function to populate the tree
        self.topic_tree.expandAll()                                 # Expands all tree nodes (expandAll()) for better visibility
        

    def update_subtopics(self, topic):                              # dynamically updates the subtopics dropdown when a user selects a main topic, Helps the user filter and choose subtopics dynamically
        self.subtopic_combo.clear()                                 # Clears subtopics whenever a new topic is selected.
        self.subtopic_combo.setEnabled(False)                       # Disables the dropdown initially until valid subtopics are found.
        
        if not topic:  # If no topic selected, exit early
            return
            
        subtopics = set()                                           # reates an empty set subtopics to store available subtopics
        
        # Find all subtopics for the selected topic
        for full_topic in self.available_topics:                    # Loops through self.available_topics, which stores all discovered MQTT topics
            parts = full_topic.split('/')                           # Splits each topic into hierarchical levels using /
            if len(parts) > 1 and parts[0] == topic:                # If the first part of the topic matches the selected topic, the rest is stored as a subtopic
                subtopics.add('/'.join(parts[1:]))
        
        # Sort subtopics naturally
        sorted_subtopics = sorted(list(subtopics))                  # Sorts the subtopics alphabetically
        
        if sorted_subtopics:
            self.subtopic_combo.addItems(sorted_subtopics)          # Adds subtopics to the dropdown (self.subtopic_combo.addItems())
            self.subtopic_combo.setEnabled(True)                    # Enables the dropdown so the user can select a subtopic
            self.subtopic_combo.setCurrentIndex(0)                  # Select first subtopic by default


    def connect_mqtt(self):                                                                 # Ensures that the MQTT listener runs in a separate thread; Prevents UI freezing when connecting to an MQTT broker
        if not self.mqtt_thread:                                                            # Ensures that the MQTT client is not already running, and Prevents duplicate MQTT connections
            self.mqtt_thread = MQTTThread(self.mqtt_host.text(), self.mqtt_port.text())     # Starts the thread between client and broker that will help running it in background
            self.mqtt_thread.message_received.connect(self.on_mqtt_message_received)        # Connects the message_received signal to on_mqtt_message_received() for handling incoming MQTT messeges
            self.mqtt_thread.connection_status.connect(self.on_mqtt_connection_status)      # Connects connection_status signal to on_mqtt_connection_status(), which updates the GUI status
            self.mqtt_thread.start()                                                        # Starts the MQTT thread (self.mqtt_thread.start()), allowing it to run in the background using the thread
            self.mqtt_status.setText("Connecting...")                                       # Updates the GUI status to indicate that it is attempting to connect.


    def on_mqtt_connection_status(self, connected, message):                                # updates the GUI when the MQTT connection status changes
        self.mqtt_connected = connected                                                     # Updates self.mqtt_connected to track whether MQTT is connected
        self.mqtt_status.setText(message)                                                   # Displays the connection message (Connected or Failed) in the GUI


    def on_mqtt_message_received(self, topic, payload):                                     # processes incoming MQTT messages
        try:
            # Process message in the main thread
            topic_parts = topic.split('/')                                                  # Splits the MQTT topic into parts using /
            self.process_topic_structure(topic_parts)                                       # Calls process_topic_structure() to update the topic hierarchy
            
            try:
                payload_data = json.loads(payload)                                          # Attempts to parse the payload as JSON
                value = payload_data.get('value', payload)                                  # Extracts value fields, if available.
                # Parse timestamp from payload or use current time as fallback
                timestamp_str = payload_data.get('timestamp')                               # Extracts timestamp fields, if available.
                if timestamp_str:
                    # Convert ISO format timestamp to Unix timestamp
                    timestamp = datetime.fromisoformat(timestamp_str).timestamp()
                else:
                    timestamp = datetime.now().timestamp()                                  # If no timestamp is provided, use the current time.
            except:
                value = payload
                timestamp = datetime.now().timestamp()
            
            try:                                                                            
                value = float(value)                                                        # Ensures that value is numeric before processing
            except:
                return
            
            self.latest_values[topic] = value                                               # Stores the latest received value for each topic
            
            # Update all frames that are monitoring this topic
            for frame_id, frame_data in self.data_buffer.items():                           # Loops through all frames in self.data_buffer
                if frame_data['topic'] == topic:                                            # Checks if the frame is monitoring the received topic
                    # Ensure time and value lists are initialized properly
                    if not isinstance(frame_data['time'], list):
                        frame_data['time'] = []
                    if not isinstance(frame_data['values'], list):
                        frame_data['values'] = []
                    
                    # Adds the new data to the frame's buffer
                    frame_data['time'].append(timestamp)
                    frame_data['values'].append(value)
                    
                    # Keep only last 1000 points for better performance
                    if len(frame_data['time']) > 1000:
                        frame_data['time'] = frame_data['time'][-1000:]
                        frame_data['values'] = frame_data['values'][-1000:]
                    
                    # Update slider range if needed for better visualization
                    if len(frame_data['time']) > 1:
                        self.plot_widgets[frame_id]['slider'].setValue(100)                 # Show most recent data
            
        except Exception as e:
            print(f"Error processing message: {str(e)}")


    def process_topic_structure(self, topic_parts):                                                         # builds the hierarchical MQTT topic structure
        current_dict = self.topic_structure                                                                 # Starts from the root of 'self.topic_structure'
        full_topic = ""
        
        for i, part in enumerate(topic_parts):                                                              # Iterates over topic parts to construct the full path
            full_topic = full_topic + "/" + part if full_topic else part
            self.available_topics.add(full_topic)                                                           # Stores the topic in self.available_topics
            
            if i < len(topic_parts) - 1:
                if part not in current_dict:                                                                # Creates sub-dictionaries for nested topics
                    current_dict[part] = {}
                current_dict = current_dict[part]
            else:
                if part not in current_dict:
                    current_dict[part] = None
        
        # Only update UI if we have new topics
        if topic_parts[0] not in [self.topic_combo.itemText(i) for i in range(self.topic_combo.count())]:
            self.update_topic_tree()
            self.update_topic_combo()


    def connect_influxdb(self):
        try:
            self.influx_client = InfluxDBClient(
                url=self.influx_url.text(),
                token=self.influx_token.text(),
                org=self.influx_org.text()
            )
            self.influx_connected = True
            
            # Test connection
            self.influx_client.ping()
            QtWidgets.QMessageBox.information(self, "Success", "Connected to InfluxDB successfully!")
            
            # Fetch available measurements and fields
            self.fetch_influx_structure()
            
        except Exception as e:
            self.influx_connected = False
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to connect to InfluxDB: {str(e)}")
            

    def fetch_influx_structure(self):
        try:
            # Query to get all measurements
            query = '''
            import "influxdata/influxdb/schema"
            schema.measurements(bucket: "{}")
            '''.format(self.influx_bucket.text())
            
            result = self.influx_client.query_api().query(query, org=self.influx_org.text())
            
            # Process results
            for table in result:
                for record in table.records:
                    measurement = record.values.get("_value")
                    
                    # Query to get fields for this measurement
                    fields_query = f'''
                    import "influxdata/influxdb/schema"
                    schema.measurementFieldKeys(
                        bucket: "{self.influx_bucket.text()}",
                        measurement: "{measurement}"
                    )
                    '''
                    
                    fields_result = self.influx_client.query_api().query(fields_query, org=self.influx_org.text())
                    
                    # Add to topic structure
                    if measurement not in self.topic_structure:
                        self.topic_structure[measurement] = {}
                    
                    for field_table in fields_result:
                        for field_record in field_table.records:
                            field = field_record.values.get("_value")
                            self.topic_structure[measurement][field] = None
                            self.available_topics.add(f"{measurement}/{field}")
            
            # Update UI
            self.update_topic_tree()
            self.update_topic_combo()
            
        except Exception as e:
            print(f"Error fetching InfluxDB structure: {str(e)}")


    def update_topic_combo(self):                               # updates the main topic dropdown (self.topic_combo) dynamically
        current_text = self.topic_combo.currentText()           # Stores the currently selected topic (current_text)
        self.topic_combo.clear()                                # Clears the topic dropdown (self.topic_combo.clear()) before updating it
        
        # Find & Add root level topics
        root_topics = set()                                 
        for topic in self.available_topics:                     # Iterates over self.available_topics (which stores all known MQTT topics)
            parts = topic.split('/')                            # Extracts only the top-level topics (i.e., before the first /)
            if len(parts) > 0:
                root_topics.add(parts[0])                       # Stores these root topics in a set (root_topics) to avoid duplicates
        
        self.topic_combo.addItems(sorted(list(root_topics)))    # Sorts the root topics alphabetically and adds them to the dropdown
        
        # Try to restore previous selection
        index = self.topic_combo.findText(current_text)         # Checks if the previously selected topic (current_text) still exists
        if index >= 0:
            self.topic_combo.setCurrentIndex(index)             # If found, it re-selects it (setCurrentIndex(index)), maintaining the user's choice

    def refresh_topics(self):                                   
        # Clear existing topics
        self.topic_structure.clear()
        self.available_topics.clear()
        
        # Refresh from both sources if connected
        if self.influx_connected:
            self.fetch_influx_structure()
        
        if self.mqtt_connected:
            self.mqtt_thread.subscribe("#")  # Re-subscribe to all topics
        
        # Update UI
        self.update_topic_tree()
        self.update_topic_combo()

    def start_plotting(self):                                           # starts plotting data for the selected topic, Allows the user to assign MQTT data streams to different frames dynamically, Ensures each frame only displays relevant data
        topic = self.topic_combo.currentText()                          # Gets the selected topic and subtopic from the dropdowns
        subtopic = self.subtopic_combo.currentText()                    
        frame_num = int(self.frame_combo.currentText().split()[-1])     # Extracts the frame number (1-6) from the dropdown
        frame_key = f'frame_{frame_num}'                                # Constructs a unique key (frame_key) for the selected frame
        
        full_topic = f"{topic}/{subtopic}" if subtopic else topic       # If a subtopic is selected, combines it with the topic (topic/subtopic), Otherwise, uses only the main topic
        
        # Initialize the empty data buffer for this selected frame
        self.data_buffer[frame_key] = {
            'time': [],
            'values': [],
            'topic': full_topic
        }
        
        # Clear existing plot : If the frame already has a plot, clears it
        if frame_key in self.plot_widgets:
            plot_widget = self.plot_widgets[frame_key]['plot']
            plot_widget.clear()
            self.plot_widgets[frame_key]['curve'] = None
            
            # Configure axes
            plot_widget.setLabel('left', 'Value')       # Labels the axis
            plot_widget.setLabel('bottom', '')          # Labels the axis
            plot_widget.showGrid(x=True, y=True)        # Enables grid lines for better readability
            
            # Reset statistics (current, max, min, etc.) to default values
            for stat in self.plot_widgets[frame_key]['stats'].values():
                stat.setText(stat.text().split(':')[0] + ": --")
        
        # Subscribe to the topic
        if self.mqtt_connected:
            self.mqtt_thread.subscribe(full_topic)      # If connected to MQTT, subscribes to the selected topic

    def update_plots(self):
        for frame_id, frame_data in self.data_buffer.items():                                               # Iterates through all frames in self.data_buffer
            if frame_id in self.plot_widgets:                                                               # Checks if the frame has a valid plot widget
                # Use frozen data if frame is frozen, otherwise use current data
                display_data = self.frozen_data[frame_id] if self.freeze_states[frame_id] else frame_data
                
                if display_data['time'] and display_data['values']:                                         # Ensures that data exists before updating the plot
                    # Retrieves the corresponding plot widget and statistics panel
                    plot_widget = self.plot_widgets[frame_id]['plot']
                    stats = self.plot_widgets[frame_id]['stats']
                    
                    # Convert all times to milliseconds for plotting
                    visible_times = [t * 1000 for t in display_data['time']]
                    visible_values = display_data['values']
                    
                    if len(visible_times) > 0 and len(visible_values) > 0:
                        # Update plot
                        plot_widget.clear()
                        
                        # Create a more visible plot style
                        pen = pg.mkPen(color=(0, 0, 255), width=1)
                        
                        # Create scatter plot item for better interaction
                        scatter = pg.ScatterPlotItem(
                            x=visible_times,
                            y=visible_values,
                            size=8, 
                            pen=pg.mkPen('w'), 
                            brush=pg.mkBrush(0, 0, 255),
                            symbol='o',
                            hoverable=True,
                            tip=None
                        )
                        
                        # Add both line and scatter plots
                        plot_widget.addItem(pg.PlotDataItem(
                            x=visible_times,
                            y=visible_values,
                            pen=pen,
                            connect='finite'
                        ))
                        plot_widget.addItem(scatter)
                        
                        # Set up hover events
                        scatter.sigHovered.connect(lambda point: self.show_hover_info(point))
                        scatter.sigClicked.connect(lambda _, points: self.show_point_info(points))
                        
                        # Calculate Y axis range with padding
                        y_min = min(visible_values)
                        y_max = max(visible_values)
                        y_padding = (y_max - y_min) * 0.1 if y_max != y_min else abs(y_max) * 0.1
                        plot_widget.setYRange(y_min - y_padding, y_max + y_padding, padding=0)
                        
                        # Calculate X axis range
                        x_min = min(visible_times)
                        x_max = max(visible_times)
                        x_padding = (x_max - x_min) * 0.1 if x_max != x_min else abs(x_max) * 0.1
                        plot_widget.setXRange(x_min - x_padding, x_max + x_padding, padding=0)
                        
                        # Update statistics : Calculates and updates real-time statistics (current, max, min, avg, std dev)
                        values_array = np.array(visible_values)
                        stats['Current'].setText(f"Current: {values_array[-1]:.2f}")
                        stats['Max'].setText(f"Max: {np.max(values_array):.2f}")
                        stats['Min'].setText(f"Min: {np.min(values_array):.2f}")
                        stats['Avg'].setText(f"Avg: {np.mean(values_array):.2f}")
                        stats['Std'].setText(f"Std: {np.std(values_array):.2f}")
                        
                        # Update title with topic and current time
                        if display_data['topic']:
                            local_time = datetime.now().astimezone()
                            current_time_str = local_time.strftime('%Y-%m-%d %H:%M:%S %Z')
                            frozen_status = " (FROZEN)" if self.freeze_states[frame_id] else ""
                            plot_widget.setTitle(f"{display_data['topic']} (Updated: {current_time_str}){frozen_status}")

    def show_point_info(self, points):                          # show tooltips when a data point is clicked or hovered
        if points and len(points) > 0:
            point = points[0]  # Get the first clicked point
            pos = point.pos()
            value = pos.x(), pos.y()  # Get the x,y-value
            
            # Create tooltip text
            tooltip_text = f'Value: {value:.2f}'
            
            # Show tooltip as a QToolTip
            QtWidgets.QToolTip.showText(
                QtGui.QCursor.pos(),
                tooltip_text
            )

    def show_hover_info(self, point):
        if point is not None:
            pos = point.pos()
            value = pos.x(), pos.y()  # Get the x,y-value
            
            # Create tooltip text
            tooltip_text = f'Value: {value:.2f}'
            
            # Show tooltip as a QToolTip
            QtWidgets.QToolTip.showText(
                QtGui.QCursor.pos(),
                tooltip_text
            )
        else:
            QtWidgets.QToolTip.hideText()

    def setup_manual_tab(self):                                 # creates the "Manual Control" tab in the GUI
        manual_tab = QtWidgets.QWidget()                        # Creates a new tab (manual_tab) for manual control settings
        layout = QtWidgets.QVBoxLayout(manual_tab)
        
        # User info : Provides a way for the operator to log who made changes and add relevant notes
        user_layout = QtWidgets.QHBoxLayout()                   # Adds a horizontal layout (user_layout) for user input
        user_layout.addWidget(QtWidgets.QLabel("Operator:"))
        self.operator = QtWidgets.QLineEdit()                   # self.operator: Field for the operator's name
        user_layout.addWidget(self.operator)
        user_layout.addWidget(QtWidgets.QLabel("Comments:"))
        self.comments = QtWidgets.QLineEdit()                   # self.comments: Field for the operator's name.
        user_layout.addWidget(self.comments)
        layout.addLayout(user_layout)
        
        # Room controls
        self.room_controls = {}                                 # Store references to room controls; A dictionary that stores UI elements for each room
        rooms = {
            "clean_room": "Clean Room",
            "cold_room": "Cold Room",
            "marta_co2_plant": "MARTA CO2 Plant"
        }
        
        for room_id, room_name in rooms.items():                # This loop creates three sections for controlling different rooms
            group = QtWidgets.QGroupBox(room_name)              # Creates a separate section (QGroupBox) for each room
            room_layout = QtWidgets.QGridLayout()               # Uses a QGridLayout to arrange controls in a table-like format
            
            # Temperature controls
            room_layout.addWidget(QtWidgets.QLabel("Temperature (°C):"), 0, 0)              # Temperature Label (QLabel): Displays "Temperature (C):"
            temp_value = QtWidgets.QLabel("?")                                              # Current Temperature Value (temp_value): Initially "?", updated dynamically
            room_layout.addWidget(temp_value, 0, 1)
            temp_spin = QtWidgets.QDoubleSpinBox()                                          # Temperature Input (QDoubleSpinBox)
            temp_spin.setRange(-50, 50)                                                     # Allows values between -50C to 50C
            room_layout.addWidget(temp_spin, 0, 2)
            set_temp = QtWidgets.QPushButton("Set Temperature")                             # PushButton : Set Temperature
            set_temp.clicked.connect(lambda checked, r=room_id: self.set_temperature(r))    # Calls self.set_temperature(room_id) when clicked
            room_layout.addWidget(set_temp, 0, 3)
            
            # Humidity controls
            room_layout.addWidget(QtWidgets.QLabel("Humidity (%):"), 1, 0)                  # Relative Humidity Label (QLabel): Displays "Humidity (%):"
            humid_value = QtWidgets.QLabel("?")                                             # Current Relative Humidity Value (temp_value): Initially "?", updated dynamically
            room_layout.addWidget(humid_value, 1, 1)
            humid_spin = QtWidgets.QDoubleSpinBox()                                         # Relative Humidity Input (QDoubleSpinBox)
            humid_spin.setRange(0, 100)                                                     # Allows values between -50C to 50C
            room_layout.addWidget(humid_spin, 1, 2)
            set_humid = QtWidgets.QPushButton("Set Humidity")                               # PushButton : Set Humidity                    
            set_humid.clicked.connect(lambda checked, r=room_id: self.set_humidity(r))      # Calls self.set_humidity(room_id) when clicked
            room_layout.addWidget(set_humid, 1, 3)
            
            # Stores references to UI elements in self.room_controls
            # Additional CO2 controls for MARTA plant
            if room_id == "marta_co2_plant":                    
                room_layout.addWidget(QtWidgets.QLabel("CO2 (ppm):"), 2, 0)
                co2_value = QtWidgets.QLabel("?")
                room_layout.addWidget(co2_value, 2, 1)
                co2_spin = QtWidgets.QDoubleSpinBox()
                # CO2 range: 0 to 2000 ppm (default value: 400 ppm)
                co2_spin.setRange(0, 2000)
                co2_spin.setValue(400)
                room_layout.addWidget(co2_spin, 2, 2)
                set_co2 = QtWidgets.QPushButton("Set CO2")
                set_co2.clicked.connect(lambda checked, r=room_id: self.set_co2(r))         # Calls self.set_co2(room_id)
                room_layout.addWidget(set_co2, 2, 3)
                
                # Store CO2 controls
                self.room_controls[room_id] = {
                    'temp_value': temp_value,
                    'temp_spin': temp_spin,
                    'humid_value': humid_value,
                    'humid_spin': humid_spin,
                    'co2_value': co2_value,
                    'co2_spin': co2_spin
                }
            else:
                self.room_controls[room_id] = {
                    'temp_value': temp_value,
                    'temp_spin': temp_spin,
                    'humid_value': humid_value,
                    'humid_spin': humid_spin
                }
            
            group.setLayout(room_layout)
            layout.addWidget(group)
        
        layout.addStretch()                                                                 # Adds spacing at the bottom (addStretch())
        self.tabs.addTab(manual_tab, "Manual Control")                                      # Adds manual_tab to the GUI

    def set_temperature(self, room_id):
        if self.mqtt_connected and room_id in self.room_controls:
            value = self.room_controls[room_id]['temp_spin'].value()                    # take the given value
            self.mqtt_thread.publish(f"command/{room_id}/temperature", str(value))      # Example topic: "command/clean_room/temperature"
            print(f"Setting {room_id} temperature to {value}°C")                        # Publishes temperature commands to MQTT

    def set_humidity(self, room_id):
        if self.mqtt_connected and room_id in self.room_controls:
            value = self.room_controls[room_id]['humid_spin'].value()
            self.mqtt_thread.publish(f"command/{room_id}/humidity", str(value))
            print(f"Setting {room_id} humidity to {value}%")

    def set_co2(self, room_id):
        if self.mqtt_connected and room_id == "marta_co2_plant":                        # Only applies to "marta_co2_plant"
            value = self.room_controls[room_id]['co2_spin'].value()
            self.mqtt_thread.publish(f"command/{room_id}/co2", str(value))
            print(f"Setting MARTA CO2 level to {value} ppm")

    def update_manual_values(self):
        try:
            for room_id, controls in self.room_controls.items():                            # Loops through each room to update UI elements
                # Update temperature display
                topic = f"{room_id}/temperature"
                if topic in self.latest_values:
                    controls['temp_value'].setText(f"{self.latest_values[topic]:.1f}")      # Updates displayed temperature
                
                # Update humidity display
                topic = f"{room_id}/humidity"
                if topic in self.latest_values:
                    controls['humid_value'].setText(f"{self.latest_values[topic]:.1f}")     # Updates humidity
                
                # Update CO2 display for MARTA plant
                if room_id == "marta_co2_plant":
                    topic = f"{room_id}/co2"
                    if topic in self.latest_values:
                        controls['co2_value'].setText(f"{self.latest_values[topic]:.1f}")   # Updates CO2 values for MARTA CO2 Plant
        except Exception as e:
            print(f"Error updating manual values: {str(e)}")

    def fetch_influx_data(self, measurement, field, start_time="-1h"):
        if not self.influx_connected:
            return None, None
            
        query = f'''
        from(bucket: "{self.influx_bucket.text()}")
          |> range(start: {start_time})
          |> filter(fn: (r) => r["_measurement"] == "{measurement}")
          |> filter(fn: (r) => r["_field"] == "{field}")
        '''
        
        result = self.influx_client.query_api().query(query, org=self.influx_org.text())
        
        times = []
        values = []
        
        for table in result:
            for record in table.records:
                times.append(record.get_time().timestamp())
                values.append(record.get_value())
                
        return times, values
        
    def clear_plot(self):                                                           # resets the selected plot, clearing both the graph and the underlying data, Allows the user to reset a specific plot without restarting the entire application, Ensures new data does not overlap with old data
        frame_num = int(self.frame_combo.currentText().split()[-1])                 # Retrieves the currently selected frame number from self.frame_combo
        frame_key = f'frame_{frame_num}'                                            # Constructs a dictionary key (frame_key) to access the corresponding data
        
        if frame_key in self.plot_widgets:
            # Clear the data buffer for this frame
            self.data_buffer[frame_key] = {'time': [], 'values': [], 'topic': None} # Resets the data buffer, removing all stored timestamps, values, and the topic
            
            # Clear the plot
            self.plot_widgets[frame_key]['plot'].clear()                            # Clears the plot from the GUI
            self.plot_widgets[frame_key]['curve'] = None                            # Removes the reference to the curve (curve = None), ensuring no ghost plots remain
            self.plot_widgets[frame_key]['plot'].setTitle("")                       # Resets the plot title
            
            # Reset statistics
            for stat in self.plot_widgets[frame_key]['stats'].values():
                stat.setText(stat.text().split(':')[0] + ": --")                    # Resets all statistics (current, max, min, etc.) displayed in the GUI
                
    def update_data_retention(self, value):        
        self.max_data_hours = value                 # Updates self.max_data_hours to store the retention period
        self.view_hours_slider.setRange(1, value)   # Ensures the time slider (view_hours_slider) stays within the updated range
        self.clean_old_data()                       # Calls clean_old_data() to remove outdated data

    def update_view_window(self, value):
        self.view_hours = value                                             # Updates the selected time window (self.view_hours)
        self.view_hours_label.setText(f"Current view: {value} hour(s)")     # Updates the UI label with the new time window
        self.update_plots()                                                 # Calls update_plots() to refresh the displayed data

    def clean_old_data(self):                                                                       # removes old data that exceeds the retention period
        current_time = time.time()
        max_age = self.max_data_hours * 3600  # Convert hours to seconds
        
        for frame_data in self.data_buffer.values():                                                # Finds all data points that are still within the retention period
            if frame_data['time']:
                # Find cutoff index
                cutoff_time = current_time - max_age
                valid_indices = [i for i, t in enumerate(frame_data['time']) if t >= cutoff_time]
                
                if valid_indices:                                                                   # Removes expired data points
                    frame_data['time'] = [frame_data['time'][i] for i in valid_indices]
                    frame_data['values'] = [frame_data['values'][i] for i in valid_indices]

    def auto_save_data(self):                                               # automatically saves data at regular intervals.
        current_time = time.time()
        if current_time - self.last_save_time >= self.auto_save_interval:   # Checks if the last save was performed before the set interval
            self.save_data(auto=True)                                       # Calls save_data(auto=True) to save data
            self.last_save_time = current_time

    def save_data(self, auto=False):                            # saves recorded data to a file
        if not os.path.exists(self.storage_path.text()):
            os.makedirs(self.storage_path.text())               # Creates the storage directory if it doesn't exist
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")    # Generates a timestamp for file naming
        format = self.storage_format.currentText().lower()
        
        prefix = "auto_" if auto else "manual_"                  
        
        # Determines the file format (CSV or JSON)

        if format == "csv":                                                                         # Saves data in CSV format.
            filename = os.path.join(self.storage_path.text(), f"{prefix}data_{timestamp}.csv")
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['frame', 'timestamp', 'value', 'topic'])
                for frame_id, frame_data in self.data_buffer.items():
                    for t, v in zip(frame_data['time'], frame_data['values']):
                        writer.writerow([frame_id, t, v, frame_data['topic']])
        else:
            filename = os.path.join(self.storage_path.text(), f"{prefix}data_{timestamp}.json")     # Saves data in JSON format
            with open(filename, 'w') as f:
                json.dump(self.data_buffer, f)

    def closeEvent(self, event):            # handles cleanup when the application is closed
        # Stop MQTT thread
        if self.mqtt_thread:
            self.mqtt_thread.stop()         # Stops the MQTT thread
            self.mqtt_thread.wait()
        
        if self.influx_client:
            self.influx_client.close()      # Closes the InfluxDB connection
        
        # Stops all timers
        self.update_timer.stop()
        self.manual_update_timer.stop()
        self.save_timer.stop()
        
        super().closeEvent(event)

    def update_time_window(self, value, frame_id):                                  # adjusts the X-axis range based on the slider position
        if frame_id in self.plot_widgets and self.data_buffer[frame_id]['time']:    # Ensures the frame exists and has data
            # Calculate time window based on slider value (0-100)
            times = self.data_buffer[frame_id]['time']
            if not times:                                                           # If no timestamps exist, exit early
                return

            # Calculates the time window based on the slider value
            total_duration = max(times) - min(times)
            window_size = total_duration * (value / 100.0)
            end_time = max(times)
            start_time = end_time - window_size                                     
            
            # Update plot x-axis range
            plot_widget = self.plot_widgets[frame_id]['plot']
            plot_widget.setXRange(start_time * 1000, end_time * 1000)

    def toggle_freeze(self, state):                                     # freezes/unfreezes the plot for the selected frame
        frame_num = int(self.frame_combo.currentText().split()[-1])
        frame_key = f'frame_{frame_num}'
        
        if state == Qt.Checked:
            # Store current data for the frame
            self.freeze_states[frame_key] = True
            if frame_key in self.data_buffer:
                self.frozen_data[frame_key] = {
                    'time': self.data_buffer[frame_key]['time'].copy() if self.data_buffer[frame_key]['time'] else [],
                    'values': self.data_buffer[frame_key]['values'].copy() if self.data_buffer[frame_key]['values'] else [],
                    'topic': self.data_buffer[frame_key]['topic']
                }
        else:
            # Unfreeze and update with current data
            self.freeze_states[frame_key] = False
            self.frozen_data[frame_key] = {'time': [], 'values': [], 'topic': None}
            self.update_plots()

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = MQTTMonitor()
    window.show()
    sys.exit(app.exec_()) 