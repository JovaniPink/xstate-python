from docs.examples.docking_controller import DockingController, FakeDrive

controller = DockingController(FakeDrive())
controller.start("bay")
controller.tick({"staged": True})
number: int = controller.phase
