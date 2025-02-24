# Code Burger
#   - import Modules
#   - Main App Objects and Settings
#   - Create all App Objects
#   - All Design Here
#   - Events
#   - Show/Run our App

## import Modules
import os
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QTreeView, QPushButton, QComboBox, QCheckBox, QMessageBox, QLineEdit, QVBoxLayout, QHBoxLayout, QMainWindow, QFileDialog
from PyQt5.QtGui import QFont
from PyQt5.QtGui import QPixmap, QStandardItemModel, QStandardItem
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import  FigureCanvasQTAgg as FigureCanvas
import sys
import paho.mqtt.client as mqtt


class MQTT_GUI(QMainWindow):
    def __init__(self):
        super(MQTT_GUI, self).__init__()

        # Make the App Objects and Settings
        self.setWindowTitle("MQTT Potter")
        self.resize(900,800)

        main_window = QWidget()

         # MQTT Plotter
# 
# [File]
# R0C0[                         Plot Setup                         ][                   v  Frame 1   v                                ]R0C1
# R1C0[ Enter MQTT server   (                               )      ][                                                                 ]R1C1
# R2C0[ Enter port          (                               )      ][                                                                 ]
# R3C0[ Check Connection [ Check!! ]  (  Conected/Not-Connected  ) ][                                                                 ]
# R4C0[                                                            ][                                                                 ]
#     [                                                            ][                                                                 ]
#     [                                                            ][                                                                 ]
#     [                                                            ][                                                                 ]
#     [                                                            ][                                                                 ]
#     [                                                            ][                                                                 ]
#     [                                                            ][                                                                 ]
#     [                                                            ][                                                                 ]
#     [                                                            ][                                                                 ]
#     [                                                            ][                                                                 ]
#     [                                                            ][                                                                 ]
#     [                                                            ][                   v  Frame 2   v                                ]R2C1
#     [                                                            ][                                                                 ]R3C1
#     [                                                            ][                                                                 ]
#     [                                                            ][                                                                 ]
# R5C0[  Select Topic           [                            v ]   ][                                                                 ]
# R6C0[  Select Channel         [                            v ]   ][                                                                 ]
# R7C0[  Set Refresh Rate (ms)  [                            v ]   ][                                                                 ]
# R8C0[  Select Frame           [                            v ]   ][                                                                 ]
#     [                                                            ][                                                                 ]
# R9C0[                     [   !! POLT !!  ]                      ][                                                                 ]
#     [                                                            ][                                                                 ]
# R10C0[   [ Can We Open Door ? ]  Door Status ( safe / unsafe )   ][                                                                 ]
# R11C0[         [ DOOR CLOSE ]  Door Status (O) / (O)             ][                                                                 ]
#     [                                                            ][                                                                 ]

        #labels
        self.lbl_plt_setup  = QLabel("Plot Setup")
        self.lbl_entr_server= QLabel("Enter MQTT Server")
        self.lbl_entr_port  = QLabel("Enter Port")
        self.lbl_chk_contn  = QLabel("Check Connecntion")
        self.lbl_slct_topic = QLabel("Select Topic")
        self.lbl_slct_chnl  = QLabel("Select Channel")
        self.lbl_rfsh_rate  = QLabel("Select Refresh Rate (ms)")
        self.lbl_st_frme    = QLabel("Set the Frame")
        self.lbl_dr_opn_sts = QLabel("Door Open Status")
        self.lbl_dr_sts     = QLabel("Door Status")
        self.lbl_frme1      = QLabel("v   Frame 1   v")
        self.lbl_frme2      = QLabel("v   Frame 2   v")

        #Push Buttons
        self.psb_chk            = QPushButton("Check !!")
        self.psb_plt            = QPushButton("PLot !!")
        self.psb_chk_dr_opn_sts = QPushButton("Can We Open Door ?")
        self.psb_dr_cls         = QPushButton("DOOR CLOSE")

        #TreeView
        self.model         = QStandardItemModel()
        self.trvw_tab      = QTreeView()
        self.trvw_tab.setModel(self.model)

        #Line Edits
        self.le_entr_server    = QLineEdit()
        self.le_entr_port      = QLineEdit()
        self.le_chk_contn      = QLineEdit()
        self.le_slct_resh_rate = QLineEdit()
        self.le_dr_opn_sts     = QLineEdit()
        self.le_dr_sts         = QLineEdit()

        #Graphs
        self.plt_frme1 = plt.figure()
        self.canvas1   = FigureCanvas(self.plt_frme1)

        self.plt_frme2 = plt.figure()
        self.canvas2   = FigureCanvas(self.plt_frme2)

        #Combo Box  
        self.cb_slct_topic      = QComboBox()
        # self.cb_slct_topic.addItem()

        self.cb_slct_chnl       = QComboBox()
        # self.cb_slct_chnl.addItem()
        
        # self.cb_slct_resh_rate  = QComboBox()
        # self.cb_slct_topic.addItem()
        
        self.cb_slct_frme      = QComboBox()
        self.cb_slct_frme.addItem("Frame 1")
        self.cb_slct_frme.addItem("Frame 2")


        #Design

        self.master_layout = QHBoxLayout()

        self.c0             = QVBoxLayout()
        self.r0c0           = QHBoxLayout()
        self.r1c0           = QHBoxLayout()
        self.r2c0           = QHBoxLayout()
        self.r3c0           = QHBoxLayout()
        self.r4c0           = QHBoxLayout()
        self.r5c0           = QHBoxLayout()
        self.r6c0           = QHBoxLayout()
        self.r7c0           = QHBoxLayout()
        self.r8c0           = QHBoxLayout()
        self.r9c0           = QHBoxLayout()
        self.r10c0          = QHBoxLayout()
        self.r11c0          = QHBoxLayout()

        self.c1             = QVBoxLayout()
        self.r0c1           = QHBoxLayout()
        self.r1c1           = QHBoxLayout()
        self.r2c1           = QHBoxLayout()
        self.r3c1           = QHBoxLayout()


        self.r0c0.addWidget(self.lbl_plt_setup, alignment = Qt.AlignCenter)
        
        self.r1c0.addWidget(self.lbl_entr_server)
        self.r1c0.addWidget(self.le_entr_server)

        self.r2c0.addWidget(self.lbl_entr_port)
        self.r2c0.addWidget(self.le_entr_port)

        self.r3c0.addWidget(self.lbl_chk_contn)
        self.r3c0.addWidget(self.psb_chk)
        self.r3c0.addWidget(self.le_chk_contn)

        self.r4c0.addWidget(self.trvw_tab)

        self.r5c0.addWidget(self.lbl_slct_topic)
        self.r5c0.addWidget(self.cb_slct_topic)

        self.r6c0.addWidget(self.lbl_slct_chnl)
        self.r6c0.addWidget(self.cb_slct_chnl)

        self.r7c0.addWidget(self.lbl_rfsh_rate)
        self.r7c0.addWidget(self.le_slct_resh_rate)

        self.r8c0.addWidget(self.lbl_st_frme)
        self.r8c0.addWidget(self.cb_slct_frme)

        self.r9c0.addWidget(self.psb_plt)

        self.r10c0.addWidget(self.psb_chk_dr_opn_sts)
        self.r10c0.addWidget(self.lbl_dr_opn_sts)
        self.r10c0.addWidget(self.le_dr_opn_sts)

        self.r11c0.addWidget(self.psb_dr_cls)
        self.r11c0.addWidget(self.lbl_dr_sts)
        self.r11c0.addWidget(self.le_dr_sts)

        self.c0.addLayout(self.r0c0)
        self.c0.addLayout(self.r1c0)
        self.c0.addLayout(self.r2c0)
        self.c0.addLayout(self.r3c0)
        self.c0.addLayout(self.r4c0)
        self.c0.addLayout(self.r5c0)
        self.c0.addLayout(self.r6c0)
        self.c0.addLayout(self.r7c0)
        self.c0.addLayout(self.r8c0)
        self.c0.addLayout(self.r9c0)
        self.c0.addLayout(self.r10c0)
        self.c0.addLayout(self.r11c0)
        
        self.r0c1.addWidget(self.lbl_frme1, alignment = Qt.AlignCenter)
        # self.r1c1.addWidget(self.canvas1)

        self.r2c1.addWidget(self.lbl_frme2, alignment = Qt.AlignCenter)
        # self.r3c1.addWidget(self.canvas2)

        self.c1.addLayout(self.r0c1)
        self.c1.addLayout(self.r1c1)
        self.c1.addLayout(self.r2c1)
        self.c1.addLayout(self.r3c1)

        self.master_layout.addLayout(self.c0, 20)
        self.master_layout.addLayout(self.c1, 80)

        #Give this layout to main window
        main_window.setLayout(self.master_layout)
        self.setCentralWidget(main_window)




## Show/Run our App
if __name__ == "__main__":
    app = QApplication([])
    main_app = MQTT_GUI()
    main_app.show()
    app.exec_()      











