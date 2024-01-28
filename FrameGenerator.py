# Author-
# Description-

import adsk.core, adsk.fusion, adsk.cam, traceback, os

defaultRodDiameter = 0.3
defaultConnectorLength = 1.5
defaultWallThickness = 0.2
defaultClearance = 0.015
cutDistanceFromStartPercent = 25 / 100  # Start at 25% of connectorLength
bitIndicatorHeightPercent = 1.2


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


class FrameGeneratorValidateInputHandler(adsk.core.ValidateInputsEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            sels = ui.activeSelections
            if len(sels) == 1:
                args.areInputsValid = True
        except:
            if ui:
                ui.messageBox("Failed:\n{}".format(traceback.format_exc()))


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
                if input.id == "entity":
                    selection = input.selection(0)
                    frameGenerator.entity = selection.entity
                elif input.id == "rodDiameter":
                    frameGenerator.rodDiameter = unitsMgr.evaluateExpression(
                        input.expression, "cm"
                    )
                elif input.id == "connectorLength":
                    frameGenerator.connectorLength = unitsMgr.evaluateExpression(
                        input.expression, "cm"
                    )
                elif input.id == "wallThickness":
                    frameGenerator.wallThickness = unitsMgr.evaluateExpression(
                        input.expression, "mm"
                    )
                elif input.id == "clearance":
                    frameGenerator.clearance = unitsMgr.evaluateExpression(
                        input.expression, "mm"
                    )

            frameGenerator.Execute()

            # ui.messageBox(
            #     f"You will need {frameGenerator.totalRodLength:.1f} cm of connection rods."
            # )
        except:
            if ui:
                ui.messageBox("Failed:\n{}".format(traceback.format_exc()))


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
                ui.messageBox("Failed:\n{}".format(traceback.format_exc()))


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

            onValidateInput = FrameGeneratorValidateInputHandler()
            cmd.validateInputs.add(onValidateInput)
            # keep the handler referenced beyond this function
            handlers.append(onExecute)
            handlers.append(onDestroy)
            # handlers.append(onValidateInput)
            # define the inputs
            inputs = cmd.commandInputs
            i1 = inputs.addSelectionInput(
                "entity", "Entity One", "Please select a BRepBody"
            )
            i1.addSelectionFilter(adsk.core.SelectionCommandInput.MeshBodies)

            initRodDiameter = adsk.core.ValueInput.createByReal(defaultRodDiameter)
            inputs.addValueInput(
                "rodDiameter", "Connection Rod Diameter", "mm", initRodDiameter
            )

            initConnectorLength = adsk.core.ValueInput.createByReal(
                defaultConnectorLength
            )
            inputs.addValueInput(
                "connectorLength", "Connector Length", "mm", initConnectorLength
            )

            initWallThickness = adsk.core.ValueInput.createByReal(defaultWallThickness)
            inputs.addValueInput(
                "wallThickness", "Connector Wall Thickness", "mm", initWallThickness
            )

            initClearance = adsk.core.ValueInput.createByReal(defaultClearance)
            inputs.addValueInput("clearance", "Print Clearance", "mm", initClearance)

        except:
            if ui:
                ui.messageBox("Failed:\n{}".format(traceback.format_exc()))


class FrameGenerator:
    _entity: adsk.fusion.MeshBody
    _visitedConnectors = {}
    _visitedRods = {}
    _nodeBodies = {}
    _nodeRods = {}
    _totalRodLength = 0.0

    def __init__(self):
        self._rodDiameter = defaultRodDiameter
        self._wallThickness = defaultWallThickness
        self._connectorLength = adsk.core.ValueInput.createByReal(
            defaultConnectorLength
        )
        self._rodNumber = 1

    # properties
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
        return self._rodDiameter / 2 + self._wallThickness + (self._clearance / 2)

    @property
    def sphereRadius(self):
        return self.connectorRadius * 1.5

    @property
    def totalRodLength(self):
        return self._totalRodLength

    @property
    def cutCylinderRadius(self) -> float:
        return self.connectorRadius - self._wallThickness / 2.0 + self._clearance / 2.0

    def create_cylinder(
        self,
        bodies,
        start: adsk.core.Point3D,
        end: adsk.core.Point3D,
        distanceFromStart: float,
        length: float,
        radius: float,
    ) -> adsk.fusion.BRepBody:
        vector = start.vectorTo(end)

        vector.normalize()
        endVector = vector.copy()
        vector.scaleBy(distanceFromStart)

        startPoint = start.copy()
        startPoint.translateBy(vector)

        endPoint = start.copy()
        endVector.scaleBy(length)

        endPoint.translateBy(endVector)

        bitIndicatorCylinder = tempBrepMgr.createCylinderOrCone(
            startPoint,
            radius,
            endPoint,
            radius,
        )

        resultCylinder = bodies.add(bitIndicatorCylinder)

        return (resultCylinder, startPoint, endPoint)

    def add_connector_marking(self, number: int, cylinder) -> adsk.fusion.BRepBody:
        bits = "{0:b}".format(number)

        start: adsk.core.Point3D = cylinder["startPoint"]
        end: adsk.core.Point3D = cylinder["endPoint"]

        initialDistance = self.sphereRadius + (self._connectorLength / 5.0) 
        bit_length = self._connectorLength / 10.0
        count = 1
        markingCylinders = []

        for bit in bits:

            distance = initialDistance + (count * bit_length)
            # one cylinder to mark the start of bits
            startIndicator, *_ = self.create_cylinder(
                    self._bodies,
                    start,
                    end,
                    0,
                    initialDistance,
                    self.connectorRadius * bitIndicatorHeightPercent,
                )
            markingCylinders.append(startIndicator)


            if bit == "1":
                bitIndicatorCylinder, startPoint, endPoint = self.create_cylinder(
                    self._bodies,
                    start,
                    end,
                    distance,
                    distance + bit_length,
                    self.connectorRadius * bitIndicatorHeightPercent,
                )
                markingCylinders.append(bitIndicatorCylinder)

            count = count + 1

        if len(markingCylinders) > 0:
            # join everything together
            result = self.combine_bodies(number, cylinder["cylinder"], markingCylinders)
            return result

        return cylinder["cylinder"]

    def combine_bodies(
        self,
        number: int,
        target: adsk.fusion.BRepBody,
        tools: list[adsk.fusion.BRepBody],
    ) -> adsk.fusion.BRepBody:
        # join with other bodies of node (sphere + n cylinders)
        node_combine = self._connectorComp.features.combineFeatures
        join_tools = adsk.core.ObjectCollection.create()

        for tool in tools:
            join_tools.add(tool)

        join_input: adsk.fusion.CombineFeatureInput = node_combine.createInput(
            target, join_tools
        )
        join_input.isNewComponent = False
        join_input.isKeepToolBodies = False
        join_input.operation = adsk.fusion.FeatureOperations.JoinFeatureOperation
        node_combine.add(join_input)

        target.name = f"Connector {number}"

        return target

    def create_connector(self, node_a_idx, node_b_idx):
        """Creates one connector with a hole
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
        shell_cylinder, startPoint, endPoint = self.create_cylinder(
            self._bodies, node_a, node_b, 0, self._connectorLength + self.sphereRadius, self.connectorRadius
        )

        if self._nodeBodies[node_a_idx]["cylinders"] == None:
            self._nodeBodies[node_a_idx]["cylinders"] = []

        self._nodeBodies[node_a_idx]["cylinders"].append(
            {
                "cylinder": shell_cylinder,
                "startPoint": startPoint,
                "endPoint": endPoint,
            }
        )

    def create_rod(self, node_a_idx: int, node_b_idx: int):
        """Creates a connection rod between two given points

        Takes into account clearances
        """
        # check if the cylinder was already created
        rodKey = (node_a_idx, node_b_idx)

        if (node_a_idx, node_b_idx) in self._visitedRods or (
            node_b_idx,
            node_a_idx,
        ) in self._visitedRods:
            return

        self._visitedRods[rodKey] = True

        node_a = self._entity.mesh.nodeCoordinates[node_a_idx]
        node_b = self._entity.mesh.nodeCoordinates[node_b_idx]

        rodStartVector = node_a.vectorTo(node_b)
        rodStartVector.normalize()
        rodStartVector.scaleBy(self._connectorLength * cutDistanceFromStartPercent)

        rodStartPoint = node_a.copy()
        rodStartPoint.translateBy(rodStartVector)

        rodEndVector = node_a.vectorTo(node_b)
        rodEndVector.subtract(rodStartVector)

        rodEndPoint = node_a.copy()
        rodEndPoint.translateBy(rodEndVector)

        rodLength = rodStartPoint.distanceTo(rodEndPoint)
        self._totalRodLength = self._totalRodLength + rodLength

        # create rod
        rod = tempBrepMgr.createCylinderOrCone(
            rodStartPoint, self.rodDiameter / 2, rodEndPoint, self.rodDiameter / 2
        )
        rodBody = self._rodBodies.add(rod)
        rodBody.name = f"Rod {self._rodNumber} - {rodLength:.1f} cm"

        # Create cut tool

        # TODO: maybe Start and End clearance? Is it necessary?
        rodCutTool = tempBrepMgr.createCylinderOrCone(
            rodStartPoint,
            self.rodDiameter / 2 + self._clearance / 2,
            rodEndPoint,
            self.rodDiameter / 2 + self._clearance / 2,
        )
        cutToolBody = self._rodBodies.add(rodCutTool)
        cutToolBody.name = f"Rod Cut {self._rodNumber}"

        self._rodNumber = self._rodNumber + 1

        if not node_a_idx in self._nodeRods:
            self._nodeRods[node_a_idx] = []

        if not node_b_idx in self._nodeRods:
            self._nodeRods[node_b_idx] = []

        self._nodeRods[node_a_idx].append(cutToolBody)
        self._nodeRods[node_b_idx].append(cutToolBody)

    def Execute(self):
        # https://help.autodesk.com/view/fusion360/ENU/?guid=GUID-0f6e9ca0-dc67-49c3-b902-baf881063e24

        self._connectorComp = createNewComponent("Connectors")
        self._bodies = self._connectorComp.bRepBodies

        self._rodComp = createNewComponent("Connection Rods")
        self._rodBodies = self._rodComp.bRepBodies

        for node_idx, node in enumerate(self._entity.mesh.nodeCoordinates):
            sphere = tempBrepMgr.createSphere(node, self.sphereRadius)
            node_body = self._bodies.add(sphere)

            if not node_idx in self._nodeBodies:
                self._nodeBodies[node_idx] = {"sphere": node_body, "cylinders": []}

        triangles = [
            self._entity.mesh.triangleNodeIndices[i * 3 : i * 3 + 3]
            for i in range(0, self._entity.mesh.triangleCount)
        ]

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

        for key in self._nodeBodies.keys():
            number = key + 1
            self.add_connector_marking(number, self._nodeBodies[key]["cylinders"][0])

            cylinders = [x["cylinder"] for x in self._nodeBodies[key]["cylinders"]]
            connectorBody = self.combine_bodies(
                number,
                self._nodeBodies[key]["sphere"],
                cylinders,
            )

            # cut rod holes
            shell_cut = self._connectorComp.features.combineFeatures
            cut_tools = adsk.core.ObjectCollection.create()

            for tool in self._nodeRods[key]:
                cut_tools.add(tool)

            cut_input: adsk.fusion.CombineFeatureInput = shell_cut.createInput(
                connectorBody, cut_tools
            )
            cut_input.isNewComponent = False
            cut_input.isKeepToolBodies = True
            cut_input.operation = adsk.fusion.FeatureOperations.CutFeatureOperation
            shell_cut.add(cut_input)

        # cleanup cut rods
        for key in self._nodeRods.keys():
            for rod in self._nodeRods[key]:
                if rod.isValid:
                    rod.deleteMe()
                # try:
                #     rod.deleteMe()
                # except:
                #     # every rod is added twice, so we ignore errors
                #     pass

        return self._entity


def run(context):
    try:
        commandDefinitions = ui.commandDefinitions
        # check the command exists or not
        cmdDef = commandDefinitions.itemById("FrameGeneratorCMDDef")
        if not cmdDef:
            resourceDir = os.path.join(
                os.path.dirname(os.path.realpath(__file__)), "resources"
            )  # absolute resource file path is specified
            cmdDef = commandDefinitions.addButtonDefinition(
                "FrameGeneratorCMDDef",
                "Frame Generator",
                "Generate a frame for a body",
                resourceDir,
            )

        onCommandCreated = FrameGeneratorCommandCreatedHandler()
        cmdDef.commandCreated.add(onCommandCreated)
        # keep the handler referenced beyond this function
        handlers.append(onCommandCreated)

        cmdDef.execute()

        # prevent this module from being terminate when the script returns, because we are waiting for event handlers to fire
        adsk.autoTerminate(False)

    except:
        if ui:
            ui.messageBox("Failed:\n{}".format(traceback.format_exc()))
