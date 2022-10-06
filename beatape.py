import asyncio

from queue import Empty
import time


import toga
import math
import aiosc
import json
from toga.style.pack import COLUMN, ROW, Pack
from beat_tracker import BeatCaller
from toga.constants import (
    CENTER,
    COLUMN,
    GREEN,
    ROW,
    WHITE,
    YELLOW,
    BLUE,
    RED,
    TRANSPARENT,
    GREY,
    DARKSLATEGREY,
    DARKKHAKI,
)
import logging


class App(toga.App):
    settings = {}

    maxSteps = 32

    outputs = set()
    stepLookup = []
    oscNameFieldIndex = 1
    currentStep = 0
    currentHighlightedSteps = set()
    metronome_next = time.time() + 2
    metronome_prev = time.time()
    osc_host = "127.0.0.1"
    osc_port = 12345
    osc_client = None
    skew = 0

    metronome_last_sync = time.time()
    bpm_label = None
    last_synced_label = None
    metronome_task = None

    @property
    def bpm(self):
        return float(self.bpm_label.text)

    @bpm.setter
    def bpm(self, bpm):
        self.bpm_label.text = "{:.2f}".format(bpm)

    async def tick(self):
        self.currentStep = (self.currentStep + 1) % self.maxSteps
        await self.goToStep(self.currentStep)

    async def goToStep(self, step):
        for outputStep in self.currentHighlightedSteps:
            outputStep.style.update(background_color=TRANSPARENT)

        messages = []
        for output in self.outputs:
            osc_pattern = output.children[self.oscNameFieldIndex].value
            outputStep = output.children[self.oscNameFieldIndex + 1 + step]
            self.currentHighlightedSteps.add(outputStep)
            outputStep.style.update(background_color=DARKSLATEGREY)
            if outputStep.value:
                messages.append((osc_pattern, aiosc.Impulse))
        if messages:
            await self.send_osc_messages(*messages)

    def changePatternName(self, widget):
        parentId = widget.parent.id
        patternSettings = self.settings.setdefault("patterns", {}
        ).setdefault(str(parentId),{"steps":{}, "pattern": ""})
        patternSettings["pattern"] = widget.value

    def enableStep(self, widget):
        _, step = widget.id.rsplit(".", 1)

        stepSet = self.stepLookup[int(step)]
        patternName = widget.parent.children[self.oscNameFieldIndex].value
        parentId = widget.parent.id
        patternSettings = self.settings.setdefault("patterns", {}
            ).setdefault(str(parentId),{"steps":{}, "pattern": ""})
        patternSettings["pattern"] =patternName

        if widget.value:
            stepSet.add(widget.parent)
            patternSettings["steps"][str(step)] = True 
        else:
            stepSet.remove(widget.parent)
            patternSettings["steps"].pop(str(step))


    def deleteOscOutput(self, widget):
        parent = widget.parent
        for stepSet in self.stepLookup:
            try:
                stepSet.remove(parent)
            except:
                pass
        self.outputs.remove(parent)
        self.settings.setdefault("patterns", {}
            ).pop(str(parent.id), "")
        for child in parent.children:
            try:
                self.currentHighlightedSteps.remove(child)
            except:
                pass
        parent.parent.remove(parent)

    def set_bpm_now(self, widget=None):
        self.setBpm(60)

    def set_bpm_fast(self, widget=None):
        self.setBpm(120)

    def set_bpm_slow(self, widget=None):
        self.setBpm(60)

    def setBpm(self, bpm, offset=None):
        self.bpm = bpm
        self.metronome_next = time.time() + 60 / self.bpm

    async def metronome(self, widget):
        while True:
            t = time.time()

            await asyncio.sleep(self.metronome_next - t)
            t = time.time()

            delta = (t - self.metronome_next) * 0.5
            self.metronome_next = t + 60 / self.bpm

            await self.tick()
    
    def changeSkew(self, widget):
        self.skew = int(widget.value)
        widget.parent.children[1].text = "skew by {}ms".format(self.skew)


    def startup(self):
        # Set up main window
        self.loadGlobalSettings()

        self.main_window = toga.MainWindow(title=self.name)

        mainBox = toga.Box(style=Pack(direction=COLUMN, padding_top=2))
        headerBox = toga.Box(style=Pack(direction=ROW, padding_top=4))
        image = toga.Image(path=str(self.paths.app / 'resources/toga.png'))
        view = toga.ImageView(id='beatape_image', image=image)
        view.style.update(height=72, width=72)
        headerBox.add(view)
        label = toga.Label("BEATAPE ")
        label.style.update(font_weight="bold", font_size=72)
        headerBox.add(label)

        self.bpm_label = toga.Label("60")
        self.bpm_label.style.update(font_weight="bold", font_size=72)
        headerBox.add(self.bpm_label)

        label = toga.Label("bpm")
        label.style.update(font_weight="bold", font_size=72)
        headerBox.add(label)



        mainBox.add(headerBox)
        settingsBox = toga.Box(style=Pack(direction=ROW, padding_top=4))


        self.settingsFileInput = toga.TextInput(id="settingsFile", value=self.settings.get("lastSettingsFile", ""))
        self.settingsFileInput.style.height = 20
        self.settingsFileInput.style.width = 400
        self.settingsFileInput.style.padding_right = 4
        settingsBox.add(self.settingsFileInput)

        loadSettingsButton = toga.Button("load", on_press=self.loadSettingsFileClick)
        loadSettingsButton.style.height = 20
        loadSettingsButton.style.padding_right = 4
        settingsBox.add(loadSettingsButton)

        saveSettingsButton = toga.Button("save", on_press=self.saveSettingsClick)
        saveSettingsButton.style.height = 20
        saveSettingsButton.style.padding_right = 4
        settingsBox.add(saveSettingsButton)
        mainBox.add(settingsBox)

        
        optionsBox = toga.Box(style=Pack(direction=ROW, padding_top=10))


        oscHost = toga.TextInput(id="osc_host", value=self.osc_host)
        oscHost.style.height = 20
        oscHost.style.width = 100
        oscHost.style.padding_right = 4
        optionsBox.add(oscHost)

        oscPort = toga.TextInput(id="osc_port", value=self.osc_port)
        oscPort.style.height = 20
        oscPort.style.width = 100
        oscPort.style.padding_right = 4
        optionsBox.add(oscPort)
        

        self.oscConnectButton = toga.Button("connect", on_press=self.setupOscClient)
        self.oscConnectButton.style.height = 20
        self.oscConnectButton.style.padding_right = 4

        optionsBox.add(self.oscConnectButton)

        mainBox.add(optionsBox)

        skewBox = toga.Box(style=Pack(direction=ROW, padding_top=10))

        skew = toga.Slider("skew", range=(-1000,1000),on_change=self.changeSkew)
        skew.style.update(width=150)
        skewBox.add(skew)

        label = toga.Label("skew by 0ms     .")
        label.style.height = 20
        label.style.padding_right = 4
        label.style.width = 200
        skewBox.add(label)

        mainBox.add(skewBox)



        self.stepsequencerBox = toga.Box(style=Pack(direction=COLUMN, padding_top=10))

        ## labels start
        labelBox = toga.Box(style=Pack(direction=ROW, padding_top=2))

        createOutputButton = toga.Button("➕", on_press=self.createOscOutputClick)
        createOutputButton.style.height = 15
        createOutputButton.style.width = 25
        createOutputButton.style.font_size = "7"
        createOutputButton.style.padding_right = 4
        createOutputButton.style.background_color = GREEN


        labelBox.add(createOutputButton)

        label = toga.Label("osc name")
        label.style.height = 20
        label.style.padding_right = 4
        label.style.width = 200
        labelBox.add(label)

        for step in range(0, self.maxSteps):
            label = toga.Label("{:2d}".format(step + 1))
            label.style.height = 20
            label.style.width = 22
            label.style.text_align = "justify"

            label.style.padding_right = 2
            if step > 0 and step % 4 == 0:
                label.style.padding_left = 7
            labelBox.add(label)
        self.stepsequencerBox.add(labelBox)
        # labels end

        for patternId, patternConfig in self.settings["patterns"].items():
            self.createOscOutput(patternId, patternConfig)

        mainBox.add(self.stepsequencerBox)

        # Add the content on the main window
        self.main_window.content = mainBox
        app.add_background_task(self.setupOscClient)
        app.add_background_task(self.metronome)
        app.add_background_task(self.bpm_receiver)

        def exit_handler(widget):
            print("exiting")

            print("exited")
            return True

        app.on_exit = exit_handler

        self.set_bpm_now()

        # Show the main window
        self.main_window.show()
    
    def createOscOutputClick(self, widget):
        patternId = str(time.time())
        patternConfig = {"pattern": "osc/pattern", "steps": {}}
        self.settings["patterns"].setdefault(patternId, patternConfig)
        self.createOscOutput(patternId, patternConfig)

    def createOscOutput(self, patternId, patternConfig):
        outputOscName = patternConfig["pattern"]
        patternSteps = patternConfig["steps"]
        outputBox = toga.Box(id=patternId, style=Pack(direction=ROW, padding_top=2))

        button = toga.Button("❌", on_press=self.deleteOscOutput)
        button.style.height = 15
        button.style.width = 25
        button.style.font_size = "7"
        button.style.padding_right = 4
        outputBox.add(button)

        oscName = toga.TextInput(
            id="%s.oscOutputName" % outputBox.id, value=outputOscName, on_change=self.changePatternName
        )
        oscName.style.height = 20
        oscName.style.width = 200
        oscName.style.padding_right = 4
        outputBox.add(oscName)

        for step in range(self.maxSteps):
            

            button = toga.Switch(
                "", id="%s.%d" % (outputBox.id, step),value=patternSteps.get(str(step), False), on_change=self.enableStep
            )
            if patternSteps.get(str(step), False):
                self.stepLookup[int(step)].add(outputBox)


            # button.style.padding_top = 4
            button.style.height = 20
            button.style.width = 15
            button.style.padding_right = 7
            button.style.padding_left = 2
            if step > 0 and step % 4 == 0:
                button.style.padding_left = 9
            button.style.alignment = "center"
            outputBox.add(button)
        self.stepsequencerBox.add(outputBox)
        self.outputs.add(outputBox)
        

    async def setupOscClient(self, widget):
        self.settings.setdefault("osc",{})["host"] = self.osc_host
        self.settings.setdefault("osc",{})["port"] = self.osc_port

    def loadSettingsFile(self, settingsFilePath):
        try:
            with open(settingsFilePath) as f:
                self.settings.update(json.load(f))
                self.maxSteps = self.settings.get("max_steps", self.maxSteps)
                self.stepLookup = [set() for i in range(self.maxSteps)]
                osc_settings = self.settings.setdefault("osc",{"host": self.osc_host, "port": self.osc_port})
                self.osc_port = osc_settings["port"]
                self.osc_host = osc_settings["host"]
        except:
            logging.exception("error loading settings file")

    def loadGlobalSettings(self, widget=None):
        path = self.paths.app / 'resources/globalSettings.json'
        self.loadSettingsFile(path)
        lastSettingsFile = self.settings.setdefault("lastSettingsFile", str(path.resolve()))
        if lastSettingsFile:
            self.loadSettingsFile(lastSettingsFile)
            
    
    def saveSettingsClick(self, widget=None):
        lastSettingsFile = self.settings["lastSettingsFile"] = self.settingsFileInput.value

        globalSettingsFile = self.paths.app / 'resources/globalSettings.json'
        with open(globalSettingsFile, 'w') as f:
            json.dump(self.settings, f)
        
        with open(lastSettingsFile, 'w') as f:
            json.dump(self.settings, f)

    def loadSettingsFileClick(self, widget):
        lastSettingsFile = self.settings["lastSettingsFile"] = self.settingsFileInput.value
        self.loadSettingsFile(lastSettingsFile)
        for output in self.outputs:
            output.parent.remove(output)
        self.outputs = set()

        self.currentHighlightedSteps = set()

        for patternId, patternConfig in self.settings["patterns"].items():
            self.createOscOutput(patternId, patternConfig)


    async def send_osc_messages(self, *messages):
        if not messages:
            return
        futures = [            aiosc.send((self.osc_host, self.osc_port), pattern, value) for (pattern, value) in messages]
        await asyncio.gather(
            *futures, return_exceptions=True
        )

    async def bpm_receiver(self, widget):
        q = asyncio.Queue()

        bc = BeatCaller(q)

        while True:
            async for s in bc.async_iter():
                bpm, next_beat_epoch = s.split(" ")
                self.bpm = float(bpm)
                self.metronome_next = float(next_beat_epoch) + (self.skew/1000.0)
                await self.send_osc_messages(
                    ("/beatape/bpm", self.bpm),
                    (
                        "/beatape/next_beat_epoch_ms",
                        math.floor(self.metronome_next * 1000.0) * 1.0,
                    ),
                )
            


def main():
    app = App("BEATAPE", "org.beeware.handlers")

    return app


if __name__ == "__main__":
    app = main()
    app.main_loop()
