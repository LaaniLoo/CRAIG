#!/usr/bin/env python3

import sys

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QPixmap, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QApplication,
    QMainWindow,
    QPushButton,
    QLabel,
    QRadioButton,
    QSizePolicy,
    QLineEdit,
    QCompleter,
    QGroupBox,
    QProgressBar,
    QMessageBox,
    QInputDialog,
    
)

from craig.data import (
    IMAGE_LAYERS,
    MORPHOLOGIES,
    SB_MORPHOLOGIES,
    get_all_sources, 
    get_source_images,
    get_closest_morph,
    validate_morphology,
    write_to_csv,
    get_saved_ids,
)

class MainWindow(QMainWindow):
    #---Setup---#
    def __init__(self):
        super().__init__()

        self.init_source_params()

        self.todo, self.saved_ids = get_saved_ids()
        self.source_idx = 0 #used to index the todo source

        # self.n_classified = len(self.saved_ids)
        self.further_entries = False
        self.morph_entries = []
        self.prev_entries = []
        self.confidence_thresh = 6

        self.pixmap = QPixmap()
        self.resize(800, 800)
        self.setWindowTitle("CRAIG")

        self.info_widget = self.create_info_widget() #setup element for source info
        self.layer_widget = self.create_layer_widget() #setup element for layer buttons

        self.morph_entry = self.create_morph_input()
        self.morph_label = self.create_morph_label()
        self.prev_label = self.create_prev_label()
        self.entry_widget = self.create_entry_widget() #setup element for classification entry

        self.image_label = self.create_image_label() 

        self.setCentralWidget(self.create_main_widget()) #combine all panels

        self.update_info_text()
        self.display_image()
        self.setup_shortcuts()

    def setup_shortcuts(self):
        undo = QShortcut(QKeySequence("Esc"), self)
        undo.activated.connect(self.undo_morph_entry)

        save = QShortcut(QKeySequence("Ctrl+s"), self)
        save.activated.connect(self.on_classification_complete)

        previous_source = QShortcut(QKeySequence("Alt+left"), self)
        previous_source.activated.connect(self.moveto_previous_source)

        next_source = QShortcut(QKeySequence("Alt+right"), self)
        next_source.activated.connect(self.moveto_next_source)

        for i,layer in enumerate(IMAGE_LAYERS.values(),start=1):
            scut = QShortcut(QKeySequence(f"Alt+{i}"), self)
            scut.activated.connect(lambda layer=layer: self.layer_buttons[layer].setChecked(True))

    #---UI building---#
    def create_image_label(self):
        image_label = QLabel("no image")
        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_label.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Ignored) #this allows the window to be resized below image size

        return image_label

    def create_layer_widget(self): #Creates the widget for the image layers with buttons
        self.layer_buttons = {}
        button_group = QGroupBox("Image layers")

        layout = QVBoxLayout(button_group)
        for name,layer in IMAGE_LAYERS.items(): #loop over all the image layer types and add a button for each one
            button = QRadioButton(name)
            if layer == self.layer:
                button.setChecked(True)
            button.toggled.connect(lambda checked,layer=layer: self.on_layer_toggled(layer,checked)) #when button is toggled, call on_layer_toggled()
            layout.addWidget(button)
            self.layer_buttons[layer] = button
            
        return button_group

    def create_morph_input(self): #creates the box to enter in the chosen morphology
        morph_entry = QLineEdit()

        display_list = [f"{code}: {name}" for name, code in MORPHOLOGIES.items()] #show both short and long names for dropdown
        completer = QCompleter(display_list)
        completer.setFilterMode(Qt.MatchFlag.MatchContains) #filter morphologies by match
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive) #entry is not case sensitive 
        morph_entry.setCompleter(completer)

        morph_entry.returnPressed.connect(lambda: QTimer.singleShot(0,self.on_morph_entry))

        return morph_entry

    def create_morph_label(self):
        morph_label = QLabel("Entries: none")
        return morph_label

    def create_prev_label(self):
        prev_label = QLabel("Previous entries: none")
        prev_label.setStyleSheet("color: #ff6b6b;")  # light red, readable on dark
        prev_label.setVisible(False)  # hidden until the further-entries stage
        return prev_label

    def create_entry_widget(self):
        entry_group = QGroupBox("Source Classification")
        layout = QVBoxLayout(entry_group)
        layout.addWidget(self.prev_label,0) #previous morph entries, is hidden until after first save
        layout.addWidget(self.morph_entry,0) #entry bar for source morphology
        layout.addWidget(self.morph_label,0) #display entered morphologies
        
        return entry_group

    def create_info_widget(self):
        info_group = QGroupBox("Source Information")
        layout = QVBoxLayout(info_group)

        self.info_labels = {}
        for name in ("source_id","saved","redshift","frequency"):
            label = QLabel("-")
            layout.addWidget(label)
            self.info_labels[name] = label
            
        self.progress = QProgressBar()
        self.progress.setRange(0,len(get_all_sources()))
        layout.addWidget(self.progress)

        return info_group

    def create_main_widget(self): #combines the source panel with the morph entry panel
        top_layout = QHBoxLayout()
        top_layout.addWidget(self.info_widget,2)
        top_layout.addWidget(self.layer_widget,1) #put the layer buttons on the LHS, 0 = no size change with window

        main_panel = QWidget()
        main_layout = QVBoxLayout(main_panel)
        main_layout.addLayout(top_layout,0)
        main_layout.addWidget(self.image_label,1) #the source image label is a widget -> set to RHS, 1 = size change with window
        main_layout.addWidget(self.entry_widget,0)

        return main_panel

    #---Event handlers---#
    def on_layer_toggled(self,layer,checked):
        if checked:
            self.layer = layer
            self.display_image()

    def on_morph_entry(self): #enter, clear text and append entry to a list
        entry_txt = self.morph_entry.text().split(": ")[0]
        closest_match = get_closest_morph(entry_txt)

        if closest_match is None:
            self.status_msg(f"No match found for entry = {entry_txt}")
            return 
        
        if closest_match in self.morph_entries:
            self.status_msg(f"{closest_match} already entered!")
            self.morph_entry.clear()

        else:
            # self.status_msg(f"Entered: {closest_match}")
            self.morph_entry.clear()
            self.morph_entries.append(closest_match)
            self.update_morph_label() #update the entered morphologies

    def undo_morph_entry(self):
        if len(self.morph_entries) > 0:
            self.status_msg(f"Removed entry: {self.morph_entries[-1]}")
            self.morph_entries.pop()
            self.update_morph_label()

        elif self.further_entries: #emptied the backup entries -> revert to old list
            self.status_msg(f"Reverting back to original entries")
            self.morph_entries = self.prev_entries.copy()
            self.prev_entries.clear()
            self.further_entries = False
            self.update_morph_label()
            self.update_prev_label() 

    def on_classification_complete(self):
        valid,msg = validate_morphology(self.morph_entries)
        if not valid:
            QMessageBox.warning(self, "Invalid Morphology", msg)
            return

        if not self.further_entries:
            label = "How confident are you in your classification?"
            self.confidence,ok = QInputDialog.getInt(self, "Confidence", label, 5, 0, 10, 1) #NOTE could this just be a bool yes or no?

            if not ok: #if exit dialog box
                return

            if self.confidence < self.confidence_thresh: #NOTE doesn't check if second entry is the same as prev
                self.further_entries = True
                self.prev_entries = self.morph_entries.copy()
                self.morph_entries.clear()
                self.update_morph_label() #update label to clear entries
                self.update_prev_label()
                return
            else:
                print("Using single entry")
                self.save_advance_source() #write to csv and advance source
        else:
            print(f"Primary: {self.prev_entries} | Backup: {self.morph_entries}")
            self.save_advance_source() #write to csv and advance source

    def reset_entries(self):
        self.further_entries = False
        self.prev_entries.clear()
        self.morph_entries.clear()
        self.update_morph_label() #update label to clear entries
        self.update_prev_label()
        self.update_info_text()
        self.display_image()
        self.morph_entry.setFocus()
        
    def moveto_previous_source(self):
        if self.source_idx == 0:
            self.status_msg("No previous sources from this session!")
            return
        self.source_idx -= 1
        # self.n_classified -= 1
        self.reset_entries()

    def moveto_next_source(self):
        if self.source_idx >= len(self.todo) - 1:
            self.status_msg("This is the last source")
            return

        if self.source_id in self.saved_ids:
            self.source_idx += 1
            # self.n_classified += 1
            self.reset_entries()
        else:
            self.status_msg("Cannot move past current source")

    def save_advance_source(self):
        if len(self.prev_entries) > 0: #set previous entries as 1st morph
            morph_1 = self.prev_entries
            morph_2 = self.morph_entries
        else:
            morph_1 = self.morph_entries
            morph_2 = ["None"]

        data_dict = {
            "source_id": self.source_id,
            "morph_1": "+".join(sorted(morph_1)),
            "morph_2": "+".join(sorted(morph_2)),
            "confidence":self.confidence,
        }

        print("Writing data to csv")        
        write_to_csv(data_dict=data_dict)
        self.saved_ids.add(self.source_id) #update the saved_ids so we can check their state

        if (self.source_idx < len(self.todo) - 1):
            # self.n_classified += 1      
            self.source_idx += 1
        all_classified = self.check_all_classified()
        self.progress.setValue(len(self.saved_ids))

        if not all_classified:  
            self.reset_entries()

    def check_all_classified(self):
        if self.source_idx >= len(self.todo):
            QMessageBox.information(self, "Complete", "Classified all sources!")
            # sys.exit()

            return True
        return False
    
    def resizeEvent(self, event): #redefine the method to rescale the image when window size changes
        super().resizeEvent(event)
        if not self.pixmap.isNull(): #rescale and reload
            scaled_pixmap = self.scale_pixmap(self.pixmap,self.image_label.size())
            self.image_label.setPixmap(scaled_pixmap)

    #---Display and update---#
    def display_image(self):
        self.pixmap = self.create_pixmap(self.image_path)
        
        if self.pixmap.isNull():
            self.status_msg(f"Failed to display {self.image_path}")
            self.image_label.setText(f"missing: {self.layer}")

        else: #if all is right, display the scaled image
            scaled_pixmap = self.scale_pixmap(self.pixmap,self.image_label.size())
            self.image_label.setPixmap(scaled_pixmap)

    def update_morph_label(self):
        joined_entries = "Entries: " + ", ".join(self.morph_entries)

        self.morph_label.setText(joined_entries)

    def update_prev_label(self):
        prev_entries = "Previous entries: " + ", ".join(self.prev_entries)
        self.prev_label.setText(prev_entries)
        self.prev_label.setVisible(self.further_entries)

    def update_info_text(self): #NOTE this needs to run on source change
        saved = self.source_id in self.saved_ids
        self.info_labels["source_id"].setText(f"Source_id: {self.source_id}")
        self.info_labels["saved"].setText(f"saved: {saved}")        
        self.info_labels["redshift"].setText(f"redshift: {self.redshift}")
        self.info_labels["frequency"].setText(f"frequency: {self.freq} GHz")

        self.progress.setValue(len(self.saved_ids))

    #---Helpers---#
    def create_pixmap(self,image_path):
        if image_path is None:
            pixmap = QPixmap()
        else:
            pixmap = QPixmap(str(image_path))
        return pixmap

    @staticmethod
    def scale_pixmap(pixmap,target_size):
        scaled_pixmap = pixmap.scaled(
            target_size, #set the width and height using the image label info
            Qt.AspectRatioMode.KeepAspectRatio, 
            Qt.TransformationMode.SmoothTransformation
        )
        return scaled_pixmap

    def init_source_params(self):
        # self.source_id = "source_1"
        self.layer = "lr"
        self.output = 50
        self.redshift = 0.02
        self.freq = 0.15

    def status_msg(self,msg):
        self.statusBar().showMessage(msg,3000)

    #---Properties---#
    @property
    def source_id(self):
        return self.todo[self.source_idx]

    @property
    def image_path(self):
        images = get_source_images(self.source_id)
        return images[self.layer]

if __name__ == "__main__":
    todo, _ = get_saved_ids()

    app = QApplication(sys.argv)
    app.styleHints().setColorScheme(Qt.ColorScheme.Dark)

    if not todo:
            QMessageBox.information(None, "Complete", "Classified all sources!")
            sys.exit()

    window = MainWindow()
    window.show()
    sys.exit(app.exec())