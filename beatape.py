import asyncio

from queue import Empty
from time import perf_counter
import toga
import aioprocessing
from toga.style.pack import COLUMN, ROW, Pack
from beats import run
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




class App(toga.App):
  
    maxSteps = 32

    outputNames = ["something", "something else", "something third"]*4
    outputs = set()
    stepLookup = [set() for i in range(maxSteps)]
    oscNameFieldIndex = 1
    currentStep = 0
    currentHighlightedSteps=set()
    metronome_next = perf_counter() + 2
    metronome_prev = perf_counter()

    metronome_last_sync = perf_counter()
    bpm_label = None
    last_synced_label = None
    metronome_task = None
    queue = aioprocessing.AioQueue()
    event = aioprocessing.AioEvent()

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
            outputStep.style.update(background_color = TRANSPARENT)

        for output in self.outputs:
            outputStep = output.children[self.oscNameFieldIndex+1+step]
            self.currentHighlightedSteps.add(outputStep)
            outputStep.style.update(background_color = DARKSLATEGREY)


    def enableStep(self, widget):
        _, step = widget.id.rsplit(".",1)

        stepSet = self.stepLookup[int(step)]
        if widget.value:
            stepSet.add(widget.parent)
        else:
            stepSet.remove(widget.parent)



    def deleteOscOutput(self, widget):
        parent = widget.parent
        for stepSet in self.stepLookup:
            try:
                stepSet.remove(parent)
            except:pass
        self.outputs.remove(parent)
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
        self.bpm=bpm
        self.metronome_next = perf_counter() + 60/self.bpm

    async def metronome(self, widget):
        while True:
            t = perf_counter()

            await asyncio.sleep(self.metronome_next-t)
            t = perf_counter()
            
            delta = (t - self.metronome_next)*0.5
            self.metronome_next = t + 60/self.bpm

            await self.tick()

    def startup(self):
        # Set up main window
        self.main_window = toga.MainWindow(title=self.name)

        mainBox = toga.Box(style=Pack(direction=COLUMN, padding_top=2))

        optionsBox = toga.Box(style=Pack(direction=ROW, padding_top=2))
        bpm_fast_button = toga.Button('set_bpm to 120', on_press=self.set_bpm_fast)
        bpm_slow_button = toga.Button('set_bpm to 60', on_press=self.set_bpm_slow)
        optionsBox.add(bpm_fast_button)
        optionsBox.add(bpm_slow_button)
        
        self.bpm_label = toga.Label('60')
        self.bpm_label.style.width=50
       
        optionsBox.add(self.bpm_label)
        mainBox.add(optionsBox)

        stepsequencerBox = toga.Box(style=Pack(direction=COLUMN, padding_top=2))

        ## labels start
        labelBox = toga.Box(style=Pack(direction=ROW, padding_top=2))
        label = toga.Label('')
        label.style.height = 20
        label.style.padding_right=4
        label.style.width = 25
        labelBox.add(label)

        label = toga.Label('osc name')
        label.style.height = 20
        label.style.padding_right=4
        label.style.width = 200
        labelBox.add(label)

        for step in range(0, self.maxSteps):
            label = toga.Label('{:2d}'.format(step+1))
            label.style.height = 20
            label.style.width = 22
            label.style.text_align = 'justify'

            label.style.padding_right=2
            if step >0 and step % 4 == 0:
                label.style.padding_left=7
            labelBox.add(label)
        stepsequencerBox.add(labelBox)
        # labels end

        for outputOscName in self.outputNames:
            outputBox = toga.Box(style=Pack(direction=ROW, padding_top=2))

            button = toga.Button('❌', on_press=self.deleteOscOutput)
            button.style.height = 15
            button.style.width = 25
            button.style.font_size = "7"
            button.style.padding_right=4
            outputBox.add(button)

            oscName = toga.TextInput(id="%s.oscOutputName" %outputBox.id, value=outputOscName)
            oscName.style.height = 20
            oscName.style.width = 200
            oscName.style.padding_right=4
            outputBox.add(oscName)


            for step in range(0, self.maxSteps):
                

                button = toga.Switch('', id="%s.%d" %(outputBox.id,step), on_change=self.enableStep)
                # button.style.padding_top = 4
                button.style.height =20
                button.style.width = 15
                button.style.padding_right=7
                button.style.padding_left=2
                if step >0 and step % 4 == 0:
                    button.style.padding_left=9
                button.style.alignment = 'center'
                outputBox.add(button)
            stepsequencerBox.add(outputBox)
            self.outputs.add(outputBox)
        
        mainBox.add(stepsequencerBox)


        # Add the content on the main window
        self.main_window.content = mainBox
        app.add_background_task(self.metronome)
        app.add_background_task(self.bpm_receiver)
        def exit_handler(widget):
            print("exiting")
            self.event.set()
            if self.p.is_alive():
                print("its alive")
                self.p.join()
            self.queue.close()

            print("exited")
            return True
            
        app.on_exit = exit_handler

        self.set_bpm_now()
       


        # Show the main window
        self.main_window.show()

    async def bpm_receiver(self, widget):

        self.p = aioprocessing.AioProcess(target=run, args=(app.queue,app.event))
        self.p.start()

        while self.p.is_alive():
            try:
                bpm = await self.queue.coro_get(timeout=1)
            except Empty: 
                continue
            if bpm is None:
                return
            self.bpm = float(bpm)
            self.metronome_next = perf_counter() + 60/self.bpm

        print("process died")
        return
  



def main():
    app =  App('Handlers', 'org.beeware.handlers')
   
    return app


if __name__ == '__main__':
    app = main()
    app.main_loop()
