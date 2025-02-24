# import sys
# import paho.mqtt.client as mqtt
# from PyQt5.QtWidgets import QApplication, QMainWindow, QMessageBox, QVBoxLayout,QTreeWidget, QTreeWidgetItem, QComboBox, QTreeWidget
# from PyQt5.QtGui import QFont
# from PyQt5.QtGui import QPixmap, QStandardItemModel, QStandardItem
# from PyQt5.QtCore import QTimer
# from mqtt_ui import MQTT_GUI  # Import the UI class from mqtt_ui.py
# import matplotlib.pyplot as plt
# from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

import sys
import paho.mqtt.client as mqtt
from PyQt5.QtWidgets import QApplication, QMainWindow, QMessageBox, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QComboBox, QTreeWidget
from PyQt5.QtGui import QFont
from PyQt5.QtGui import QPixmap, QStandardItemModel, QStandardItem
from PyQt5.QtCore import QTimer
from mqtt_ui import MQTT_GUI  # Import the UI class from mqtt_ui.py
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import time  # Required for time function


class MQTTApp(MQTT_GUI):
    def __init__(self):
        super().__init__()
        
        # Store MQTT settings
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        # Connect UI elements to functions
        # self.cb_slct_topic = self.findChild(QComboBox, 'cb_slct_topic')
        # self.trvw_tab = self.findChild(QTreeWidget, 'trvw_tab')

        self.psb_chk.clicked.connect(self.check_mqtt_connection)
        self.cb_slct_topic.currentIndexChanged.connect(self.load_channels)
        self.le_slct_resh_rate.textChanged.connect(self.set_refresh_rate)
        self.cb_slct_frme.currentIndexChanged.connect(self.set_active_canvas)
        
        # Set up Matplotlib canvases
        self.figure1, self.ax1 = plt.subplots()
        self.canvas1 = FigureCanvas(self.figure1)
        self.figure2, self.ax2 = plt.subplots()
        self.canvas2 = FigureCanvas(self.figure2)
        
        # Add canvases to the UI
        self.r1c1.addWidget(self.canvas1)
        self.r3c1.addWidget(self.canvas2)
        
        # Timer for refreshing the plot
        self.refresh_rate = 1000  # Default 1 second
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(self.refresh_rate)
        
        # Selected canvas
        self.active_canvas = self.canvas1
        
        # Data storage
        self.data_x = []
        self.data_y = []
        self.times = []
        self.temperatures = []
        

    def check_mqtt_connection(self):
        """Check MQTT connection and update status."""
        self.mqtt_broker = self.le_entr_server.text().strip()
        self.mqtt_port = int(self.le_entr_port.text().strip())
        
        if not self.mqtt_broker:
            QMessageBox.warning(self, "Error", "Please enter an MQTT server IP.")
            return
        
        try:
            self.client.connect(self.mqtt_broker, self.mqtt_port, 60)
            self.client.loop_start()
            # self.le_chk_contn.setText("Connected")
            print(f"Connecting to {self.mqtt_broker}:{self.mqtt_port}...")
            self.le_chk_contn.setText("Connecting...")
        except Exception as e:
            self.le_chk_contn.setText("Failed/Dis-Connected")
            print(f"Failed to connect: {str(e)}")  # Debugging line
            QMessageBox.warning(self, "Error", f"Failed: {str(e)}")
    
    def on_connect(self, client, userdata, flags, rc):
        """Handle successful MQTT connection."""
        print(f"Connection result code: {rc}")  # Debugging line

        if rc == 0:
            self.le_chk_contn.setText("Connected")
            self.client.subscribe("#")  # Subscribe to all topics
            print("Subscribed to # topic.")  # Debugging line
        else:
            self.le_chk_contn.setText(f"Failed (Code {rc})")
            print(f"Failed to connect: Code {rc}")  # Debugging line
    
    def on_message(self, client, userdata, msg):
        """Display available topics in the tree view and allow topic selection."""
        print(f"Received message: {msg.topic} -> {msg.payload}")  # Debugging line
        topic = msg.topic
        print(f"Received message on topic: {topic}")  # Debugging line
        # global self.times, temperatures
        # Decode and store data
        temperature = float(msg.payload.decode())
        self.times.append(time.time())  # Use timestamps
        self.temperatures.append(temperature)
        
        # Update ComboBox and TreeView with the new topic
        if topic not in [self.cb_slct_topic.itemText(i) for i in range(self.cb_slct_topic.count())]:
            print(f"Adding topic {topic} to ComboBox and TreeView")  # Debugging line
            self.cb_slct_topic.addItem(topic)
            item = QStandardItem(topic)
            self.model.appendRow(item)
            # self.trvw_tab.addTopLevelItem(item)
            self.trvw_tab.expandAll()  # Expand TreeView to show added topics
    
    def load_channels(self):
        """Load channels based on selected topic."""
        selected_topic = self.cb_slct_topic.currentText()
        self.cb_slct_chnl.clear()
        self.cb_slct_chnl.addItem("Channel 1")  # Example
        self.cb_slct_chnl.addItem("Channel 2")  # Example
    
    def set_refresh_rate(self):
        """Set the refresh rate based on user selection."""
        rate_text = self.le_slct_resh_rate.text().strip()
        if rate_text.isdigit():
            self.refresh_rate = int(rate_text)
            self.timer.setInterval(self.refresh_rate)
    
    def set_active_canvas(self):
        """Set the active canvas based on user selection."""
        selected_frame = self.cb_slct_frme.currentText()
        if selected_frame == "Frame 1":
            self.active_canvas = self.canvas1
        else:
            self.active_canvas = self.canvas2
    
    def update_plot(self):
        """Update the selected Matplotlib plot dynamically with growing data."""

        # self.data_x.append(len(self.data_x))  # Incremental x-axis
        # self.data_y.append(len(self.data_y))  # Example data growth
        # print(self.data_x,'\t\t',self.data_y)
        self.active_canvas.figure.clear()
        ax = self.active_canvas.figure.add_subplot(111)
        ax.plot(self.times, self.temperatures, marker='o', linestyle='-', color='b')
        ax.set_title("MQTT Live Data")
        ax.set_xlabel("Time")
        ax.set_ylabel("Temperature (°C)")
        self.active_canvas.draw()

# Run Application
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MQTTApp()
    window.show()
    sys.exit(app.exec_())
