#Author-
#Description-

import adsk.core, adsk.fusion, adsk.cam, traceback, os

# global set of event handlers to keep them referenced for the duration of the command
handlers = []
app = adsk.core.Application.get()
if app:
    ui = app.userInterface

    doc = app.activeDocument
    d = doc.design
    rootComp: adsk.fusion.Component = d.rootComponent
    tempBrepMgr = adsk.fusion.TemporaryBRepManager.get()  
    bodies = rootComp.bRepBodies

# TODO: detect if history is on and guide user to disable it

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
    # UNIT: cm
    # TODO: configurable
    rod_diameter = .4

    cylinder_length = 2.5
    wall_thickness = .1
    cylinder_radius = rod_diameter / 2 + wall_thickness
    sphere_radius = cylinder_radius * 1.5

    entity: adsk.fusion.MeshBody
    visited_cylinders = {}
    node_bodies = {}

    def add_cylinder(self, node_a_idx, node_b_idx):
        # check if the cylinder was already created
        cylinder_key = (node_a_idx, node_b_idx)

        if cylinder_key in self.visited_cylinders:
            return

        self.visited_cylinders[cylinder_key] = True

        node_a = self.entity.mesh.nodeCoordinates[node_a_idx]
        node_b = self.entity.mesh.nodeCoordinates[node_b_idx]

        # create cylinder (shell)
        start_vector_a_b = node_a.vectorTo(node_b)
        start_vector_a_b.normalize()
        start_vector_a_b.scaleBy(self.sphere_radius * 0.75)

        end_vector_a_b = node_a.vectorTo(node_b)
        end_vector_a_b.normalize()
        end_vector_a_b.scaleBy(self.cylinder_length)

        start_point_a_b = node_a.copy()
        start_point_a_b.translateBy(start_vector_a_b)

        target_point_a_b = node_a.copy()
        target_point_a_b.translateBy(end_vector_a_b)
        
        cylinder = tempBrepMgr.createCylinderOrCone(start_point_a_b, self.cylinder_radius, target_point_a_b, self.cylinder_radius)
        shell_cylinder = bodies.add(cylinder)
        
        # create cylinder to cut out
        cylinder_tool_body = tempBrepMgr.createCylinderOrCone(start_point_a_b, self.cylinder_radius-self.wall_thickness, target_point_a_b, self.cylinder_radius-self.wall_thickness)
        tool_body = bodies.add(cylinder_tool_body)

        # cut hole
        shell_cut = rootComp.features.combineFeatures
        cut_tools = adsk.core.ObjectCollection.create()
        cut_tools.add(tool_body)
        cut_input: adsk.fusion.CombineFeatureInput = shell_cut.createInput(shell_cylinder, cut_tools)
        cut_input.isNewComponent = False
        cut_input.isKeepToolBodies = False
        cut_input.operation = adsk.fusion.FeatureOperations.CutFeatureOperation
        shell_cut.add(cut_input)

        # join with other bodies of node (sphere + n cylinders)
        node_combine = rootComp.features.combineFeatures
        join_tools = adsk.core.ObjectCollection.create()
        join_tools.add(shell_cylinder)
        join_input: adsk.fusion.CombineFeatureInput = node_combine.createInput(self.node_bodies[node_a_idx], join_tools)
        join_input.isNewComponent = False
        join_input.isKeepToolBodies = False
        join_input.operation = adsk.fusion.FeatureOperations.JoinFeatureOperation
        node_combine.add(join_input)

        # create rod
        # TODO: shorten rod length to match cutout
        # TODO: Naming / move rods to own component
        # TODO: move to separate component
        rod = tempBrepMgr.createCylinderOrCone(node_a, self.cylinder_radius-self.wall_thickness, node_b, self.cylinder_radius-self.wall_thickness)
        bodies.add(rod)


    def Execute(self, entity: adsk.fusion.MeshBody):

        self.entity = entity
        # https://help.autodesk.com/view/fusion360/ENU/?guid=GUID-0f6e9ca0-dc67-49c3-b902-baf881063e24

        for node_idx, node in enumerate(entity.mesh.nodeCoordinates):
            sphere = tempBrepMgr.createSphere(node, self.sphere_radius)
            node_body = bodies.add(sphere)
            self.node_bodies[node_idx] = node_body


        triangles = [entity.mesh.triangleNodeIndices[i*3:i*3+3] for i in range(0, entity.mesh.triangleCount)]

        # A -- B
        #  \  /
        #   C

        for triangle in triangles:
            self.add_cylinder(triangle[0], triangle[1])
            self.add_cylinder(triangle[0], triangle[2])
            self.add_cylinder(triangle[1], triangle[2])
           
            self.add_cylinder(triangle[1], triangle[0])
            self.add_cylinder(triangle[2], triangle[0])
            self.add_cylinder(triangle[2], triangle[1])


        return self.entity

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
