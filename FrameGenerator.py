#Author-
#Description-

import adsk.core, adsk.fusion, adsk.cam, traceback, os

defaultRodDiameter = .3
defaultConnectorLength = 2.5
defaultWallThickness = .2
defaultClearance = .015

def createNewComponent(name: str):
    # Get the active design.
    product = app.activeProduct
    design = adsk.fusion.Design.cast(product)
    rootComp = design.rootComponent
    allOccs = rootComp.occurrences
    newOcc = allOccs.addNewComponent(adsk.core.Matrix3D.create())
    newOcc.component.name = name
    return newOcc.component

# global set of event handlers to keep them referenced for the duration of the command
handlers = []
app = adsk.core.Application.get()
if app:

    # Disable history otherwise temp brepbody is not working
    des = adsk.fusion.Design.cast(app.activeProduct)
    des.designType = adsk.fusion.DesignTypes.DirectDesignType  

    ui = app.userInterface

    doc = app.activeDocument
    d = doc.design
    
    rootComp: adsk.fusion.Component = d.rootComponent
    tempBrepMgr = adsk.fusion.TemporaryBRepManager.get()  

    connectorComp = createNewComponent("Connectors")
    bodies = connectorComp.bRepBodies

    rodComp = createNewComponent("Connection Rods")
    rodBodies = rodComp.bRepBodies
    

# class FrameGeneratorValidateInputHandler(adsk.core.ValidateInputsEventHandler):
#     def __init__(self):
#         super().__init__()
       
#     def notify(self, args):
#         try:
#             sels = ui.activeSelections
#             if len(sels) == 1:
#                 args.areInputsValid = True
#         except:
#             if ui:
#                 ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))

class FrameGeneratorCommandExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            unitsMgr = app.activeProduct.unitsManager
            command = args.firingEvent.sender
            inputs = command.commandInputs

            frameGenerator = FrameGenerator()
            for input in inputs:
                if input.id == 'entity':
                    selection = input.selection(0)
                    frameGenerator.entity = selection.entity
                elif input.id == 'rodDiameter':
                    frameGenerator.rodDiameter = unitsMgr.evaluateExpression(input.expression, "cm")
                elif input.id == 'connectorLength':
                    frameGenerator.connectorLength = unitsMgr.evaluateExpression(input.expression, "cm")
                elif input.id == 'wallThickness':
                    frameGenerator.wallThickness = unitsMgr.evaluateExpression(input.expression, "mm")
                elif input.id == 'clearance':
                    frameGenerator.clearance = unitsMgr.evaluateExpression(input.expression, "mm")

            frameGenerator.Execute()
        except:
            if ui:
                ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))


class FrameGeneratorCommandDestroyHandler(adsk.core.CommandEventHandler):
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

class FrameGeneratorCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            cmd = args.command
            onExecute = FrameGeneratorCommandExecuteHandler()
            cmd.execute.add(onExecute)
            onDestroy = FrameGeneratorCommandDestroyHandler()
            cmd.destroy.add(onDestroy)

            # onValidateInput = FrameGeneratorValidateInputHandler()
            # cmd.validateInputs.add(onValidateInput)
            # keep the handler referenced beyond this function
            handlers.append(onExecute)
            handlers.append(onDestroy)
            # handlers.append(onValidateInput)
            #define the inputs
            inputs = cmd.commandInputs
            i1 = inputs.addSelectionInput('entity', 'Entity One', 'Please select a BRepBody')
            i1.addSelectionFilter(adsk.core.SelectionCommandInput.MeshBodies)

            initRodDiameter = adsk.core.ValueInput.createByReal(defaultRodDiameter)
            inputs.addValueInput('rodDiameter', 'Connection Rod Diameter', 'mm', initRodDiameter)

            initConnectorLength = adsk.core.ValueInput.createByReal(defaultConnectorLength)
            inputs.addValueInput('connectorLength', 'Connector Length', 'mm', initConnectorLength)

            initWallThickness = adsk.core.ValueInput.createByReal(defaultWallThickness)
            inputs.addValueInput('wallThickness', 'Connector Wall Thickness', 'mm', initWallThickness)

            initClearance = adsk.core.ValueInput.createByReal(defaultClearance)
            inputs.addValueInput('clearance', 'Print Clearance', 'mm', initClearance)

        except:
            if ui:
                ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))

class FrameGenerator:
    # UNIT: cm
    # TODO: configurable

    _entity: adsk.fusion.MeshBody
    _visitedConnectors = {}
    _visitedRods = {}
    _nodeBodies = {}

    def __init__(self):
        self._rodDiameter = defaultRodDiameter
        self._wallThickness = defaultWallThickness
        self._connectorLength = adsk.core.ValueInput.createByReal(defaultConnectorLength)
        self._rodNumber = 1

    #properties      
    @property
    def entity(self):
        return self._entity
    @entity.setter
    def entity(self, value: adsk.fusion.MeshBody):
        self._entity = value

    @property
    def rodDiameter(self):
        return self._rodDiameter
    @rodDiameter.setter
    def rodDiameter(self, value):
        self._rodDiameter = value

    @property
    def wallThickness(self):
        return self._wallThickness
    @wallThickness.setter
    def wallThickness(self, value):
        self._wallThickness = value

    @property
    def connectorLength(self):
        return self._connectorLength
    @connectorLength.setter
    def connectorLength(self, value):
        self._connectorLength = value

    @property
    def clearance(self):
        return self._clearance
    @clearance.setter
    def clearance(self, value):
        self._clearance = value

    @property
    def connectorRadius(self):
        return self._rodDiameter / 2 + self._wallThickness / 2

    @property
    def sphereRadius(self):
        return self.connectorRadius * 1.5

    def create_connector(self, node_a_idx, node_b_idx):
        """ Creates one connector with a hole
        :type self:
        :param self:
    
        :type node_a_idx:
        :param node_a_idx:
    
        :type node_b_idx:
        :param node_b_idx:
    
        :raises:
    
        :rtype:
        """
        # check if the cylinder was already created
        connectorKey = (node_a_idx, node_b_idx)

        if connectorKey in self._visitedConnectors:
            return

        self._visitedConnectors[connectorKey] = True

        node_a = self._entity.mesh.nodeCoordinates[node_a_idx]
        node_b = self._entity.mesh.nodeCoordinates[node_b_idx]

        # create cylinder (shell)
        start_vector_a_b = node_a.vectorTo(node_b)
        start_vector_a_b.normalize()
        start_vector_a_b.scaleBy(self.sphereRadius * 0.75)

        end_vector_a_b = node_a.vectorTo(node_b)
        end_vector_a_b.normalize()
        end_vector_a_b.scaleBy(self._connectorLength)

        start_point_a_b = node_a.copy()
        start_point_a_b.translateBy(start_vector_a_b)

        target_point_a_b = node_a.copy()
        target_point_a_b.translateBy(end_vector_a_b)
        
        cylinder = tempBrepMgr.createCylinderOrCone(start_point_a_b, self.connectorRadius, target_point_a_b, self.connectorRadius)
        shell_cylinder = bodies.add(cylinder)
        
        # create cylinder to cut out
        cylinder_tool_body = tempBrepMgr.createCylinderOrCone(start_point_a_b, self.connectorRadius-self._wallThickness/2+self._clearance/2, target_point_a_b, self.connectorRadius-self._wallThickness/2+self._clearance/2)
        tool_body = bodies.add(cylinder_tool_body)

        # cut hole
        shell_cut = connectorComp.features.combineFeatures
        cut_tools = adsk.core.ObjectCollection.create()
        cut_tools.add(tool_body)
        cut_input: adsk.fusion.CombineFeatureInput = shell_cut.createInput(shell_cylinder, cut_tools)
        cut_input.isNewComponent = False
        cut_input.isKeepToolBodies = False
        cut_input.operation = adsk.fusion.FeatureOperations.CutFeatureOperation
        shell_cut.add(cut_input)

        # join with other bodies of node (sphere + n cylinders)
        node_combine = connectorComp.features.combineFeatures
        join_tools = adsk.core.ObjectCollection.create()
        join_tools.add(shell_cylinder)
        join_input: adsk.fusion.CombineFeatureInput = node_combine.createInput(self._nodeBodies[node_a_idx], join_tools)
        join_input.isNewComponent = False
        join_input.isKeepToolBodies = False
        join_input.operation = adsk.fusion.FeatureOperations.JoinFeatureOperation
        node_combine.add(join_input)


    def create_rod(self, node_a_idx: int, node_b_idx: int):
        # check if the cylinder was already created
        rodKey = (node_a_idx, node_b_idx)

        if (node_a_idx, node_b_idx) in self._visitedRods or \
           (node_b_idx, node_a_idx) in self._visitedRods:
            return

        self._visitedRods[rodKey] = True

        node_a = self._entity.mesh.nodeCoordinates[node_a_idx]
        node_b = self._entity.mesh.nodeCoordinates[node_b_idx]

        start_vector_a_b = node_a.vectorTo(node_b)
        start_vector_a_b.normalize()
        start_vector_a_b.scaleBy(self.sphereRadius * 1.1)  # TODO: clearance

        start_point_a_b = node_a.copy()
        start_point_a_b.translateBy(start_vector_a_b)



        end_vector_a_b = node_a.vectorTo(node_b)
        # end_vector_a_b.normalize()
        # end_vector_a_b.scaleBy(self.sphereRadius * 0.75)  # TODO: clearance
        end_vector_a_b.subtract(start_vector_a_b)

        end_point_a_b = node_a.copy()
        end_point_a_b.translateBy(end_vector_a_b)

        # end_vector_a_b = node_a.vectorTo(node_b)
        # end_vector_a_b.normalize()
        # end_vector_a_b.scaleBy(self.sphereRadius * 0.75) # TODO: clearance
        
        # end = start_point_a_b.copy()

        # vec = node_b.vectorTo(start_point_a_b)


        # vec.subtract(start_vector_a_b)

        # target_point_a_b = node_a.copy()
        # target_point_a_b.translateBy(vec)

        rodLength = start_point_a_b.distanceTo(end_point_a_b)

        # create rod
        rod = tempBrepMgr.createCylinderOrCone(start_point_a_b, self.rodDiameter/2, end_point_a_b, self.rodDiameter/2)
        addedBody = rodBodies.add(rod)
        addedBody.name = f"Rod {self._rodNumber} - {rodLength:.1f} cm"
        self._rodNumber = self._rodNumber + 1

    def Execute(self):
        # https://help.autodesk.com/view/fusion360/ENU/?guid=GUID-0f6e9ca0-dc67-49c3-b902-baf881063e24

        for node_idx, node in enumerate(self._entity.mesh.nodeCoordinates):
            sphere = tempBrepMgr.createSphere(node, self.sphereRadius)
            node_body = bodies.add(sphere)
            self._nodeBodies[node_idx] = node_body

        triangles = [self._entity.mesh.triangleNodeIndices[i*3:i*3+3] for i in range(0, self._entity.mesh.triangleCount)]

        for triangle in triangles:
            # one direction
            self.create_connector(triangle[0], triangle[1])
            self.create_connector(triangle[0], triangle[2])
            self.create_connector(triangle[1], triangle[2])

            # the other direction
            self.create_connector(triangle[1], triangle[0])
            self.create_connector(triangle[2], triangle[0])
            self.create_connector(triangle[2], triangle[1])

            # create rods for the triangle
            self.create_rod(triangle[0], triangle[1])
            self.create_rod(triangle[0], triangle[2])
            self.create_rod(triangle[1], triangle[2])

        return self._entity

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

        onCommandCreated = FrameGeneratorCommandCreatedHandler()
        cmdDef.commandCreated.add(onCommandCreated)
        # keep the handler referenced beyond this function
        handlers.append(onCommandCreated)
        
        cmdDef.execute()

        # prevent this module from being terminate when the script returns, because we are waiting for event handlers to fire
        adsk.autoTerminate(False)

    except:
        if ui:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))
