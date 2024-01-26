#Author-
#Description-

import adsk.core, adsk.fusion, adsk.cam, traceback, os

# global set of event handlers to keep them referenced for the duration of the command
handlers = []
app = adsk.core.Application.get()
if app:
    ui = app.userInterface

class IntersectionValidateInputHandler(adsk.core.ValidateInputsEventHandler):
    def __init__(self):
        super().__init__()
       
    def notify(self, args):
        try:
            sels = ui.activeSelections
            if len(sels) == 1:
                args.areInputsValid = True
        except:
            if ui:
                ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))

class IntersectionCommandExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            command = args.firingEvent.sender
            inputs = command.commandInputs

            input0 = inputs[0]
            sel0 = input0.selection(0)

            frameGenerator = FrameGenerator()
            frameGenerator.Execute(sel0.entity)
        except:
            if ui:
                ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))


class IntersectionCommandDestroyHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            # when the command is done, terminate the script
            # this will release all globals which will remove all event handlers
            adsk.terminate()
        except:
            if ui:
                ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))

class IntersectionCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            cmd = args.command
            onExecute = IntersectionCommandExecuteHandler()
            cmd.execute.add(onExecute)
            onDestroy = IntersectionCommandDestroyHandler()
            cmd.destroy.add(onDestroy)

            onValidateInput = IntersectionValidateInputHandler()
            cmd.validateInputs.add(onValidateInput)
            # keep the handler referenced beyond this function
            handlers.append(onExecute)
            handlers.append(onDestroy)
            handlers.append(onValidateInput)
            #define the inputs
            inputs = cmd.commandInputs
            i1 = inputs.addSelectionInput('entity', 'Entity One', 'Please select a BRepBody')

            i1.addSelectionFilter(adsk.core.SelectionCommandInput.MeshBodies)
            # i1.addSelectionFilter(adsk.core.SelectionCommandInput.Occurrences)
            # i1.addSelectionFilter(adsk.core.SelectionCommandInput.RootComponents)

        except:
            if ui:
                ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))

class FrameGenerator:
    def Execute(self, entity: adsk.fusion.MeshBody):

        geom = entity

        doc = app.activeDocument
        d = doc.design
        rootComp: adsk.fusion.Component = d.rootComponent

        sketches = rootComp.sketches
        xyPlane = rootComp.xYConstructionPlane
        xzPlane = rootComp.xZConstructionPlane
        sketch = sketches.add(xyPlane)

        tempBrepMgr = adsk.fusion.TemporaryBRepManager.get()  
        bodies = rootComp.bRepBodies

        # https://help.autodesk.com/view/fusion360/ENU/?guid=GUID-0f6e9ca0-dc67-49c3-b902-baf881063e24

        #array_split(mesh.triangles_dingsdums, mesh.count_triangle)

        # def chunks(lst, n):
        #     for i in range(0, len(lst), n):
        #         yield lst[i:i + n]

        # triangles = chunks(entity.mesh.triangleNodeIndices, 3)
        triangles = [entity.mesh.triangleNodeIndices[i*3:i*3+3] for i in range(0, entity.mesh.triangleCount)]
        vertices = {}


        # A -- B
        #  \  /
        #   C

        # FIXME: 
        for triangle in triangles:
            n1, n2, n3 = triangle
            
            if n1 not in vertices:
                vertices[n1] = []
            
            if n2 not in vertices[n1]:
                vertices[n1].append(n2)

            if n3 not in vertices[n1]:
                vertices[n1].append(n3)

        for idx, node in entity.mesh.nodeCoordinates:
            # Create sphere
            sphere = tempBrepMgr.createSphere(node, .3)
            bodies.add(sphere)

        return geom
def run(context):
    try:
        # app = adsk.core.Application.get()
        # ui  = app.userInterface
        # ui.messageBox('Hello script')

        commandDefinitions = ui.commandDefinitions
        # check the command exists or not
        cmdDef = commandDefinitions.itemById('FrameGeneratorCMDDef')
        if not cmdDef:
            resourceDir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'resources') # absolute resource file path is specified
            cmdDef = commandDefinitions.addButtonDefinition('FrameGeneratorCMDDef',
                    'Frame Generator',
                    'Generate a frame for a body',
                    resourceDir)

        onCommandCreated = IntersectionCommandCreatedHandler()
        cmdDef.commandCreated.add(onCommandCreated)
        # keep the handler referenced beyond this function
        handlers.append(onCommandCreated)
        
        cmdDef.execute()

        # prevent this module from being terminate when the script returns, because we are waiting for event handlers to fire
        adsk.autoTerminate(False)

    except:
        if ui:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))
