from typing import List

import urwid

from ovshell import api
from ovshell import widget


class SetupApp(api.App):
    name = "setup"
    title = "Setup"
    description = "System setup and calibration wizard"
    priority = 10

    def __init__(self, shell: api.OpenVarioShell):
        self.shell = shell

    def launch(self) -> None:
        act = SetupActivity(self.shell)
        self.shell.screen.push_activity(act)


class WizardStepWidget(urwid.WidgetWrap):
    signals = ["next"]
    title: str

    def next_step(self) -> None:
        self._emit("next")

    def make_next_button(self, title: str) -> urwid.Widget:
        btn = widget.PlainButton(title)
        urwid.connect_signal(btn, "click", self._on_next)
        return btn

    def _on_next(self, w: urwid.Widget) -> None:
        self.next_step()


class WelcomeWizardStep(WizardStepWidget):
    title = "Welcome to Openvario"

    def __init__(self, shell: api.OpenVarioShell) -> None:
        self.shell = shell

        welcome_msg = [
            "This wizard will guide you through setting up your ",
            ("highlight", "Openvario"),
            " device.",
        ]

        content = urwid.Pile(
            [
                ("pack", urwid.Text(welcome_msg)),
                ("pack", urwid.Divider()),
                ("pack", _button_row([self.make_next_button("Start")]),),
            ]
        )
        super().__init__(content)


class OrientationWizardStep(WizardStepWidget):
    title = "Device orientation"

    def __init__(self, shell: api.OpenVarioShell) -> None:
        self.shell = shell
        self.shell = shell

        msg = [
            "Orient your Openvario device the way it will be mounted on "
            "your instrument panel. Press ",
            ("highlight", "↓"),
            " and ",
            ("highlight", "↑"),
            " until orientation looks right. Press ",
            ("highlight", "Enter"),
            " to confirm.",
        ]

        content = urwid.Pile(
            [
                ("pack", _button_row([self.make_next_button("Skip")]),),
                ("pack", urwid.Divider()),
                ("pack", urwid.Text(msg)),
            ]
        )
        super().__init__(content)


class CalibrateTouchWizardStep(WizardStepWidget):
    title = "Touch screen calibration"

    def __init__(self, shell: api.OpenVarioShell) -> None:
        self.shell = shell

        msg = [
            "If your Openvario is equipped with a touch-screen, ",
            "it needs to be calibrated. You will need to press the indicated ",
            "areas of the screen. It is recommended to press resistive ",
            "touch-screen with your fingernail.",
            "\n\n",
            "If touch-screen is not installed, skip this step.",
        ]

        cal_btn = widget.PlainButton("Calibrate")

        content = urwid.Pile(
            [
                ("pack", _button_row([self.make_next_button("Skip")]),),
                ("pack", urwid.Divider()),
                ("pack", urwid.Text(msg)),
                ("pack", urwid.Divider()),
                ("pack", _button_row([cal_btn]),),
            ]
        )
        super().__init__(content)


class CalibrateSensorsWizardStep(WizardStepWidget):
    title = "Sensor calibration"

    def __init__(self, shell: api.OpenVarioShell) -> None:
        self.shell = shell

        msg = [
            "If your Openvario has sensorboard connected, calibrate sensors here. ",
            "\n\n",
            "If sensors are not installed, skip this step.",
        ]

        cal_btn = widget.PlainButton("Calibrate")

        content = urwid.Pile(
            [
                ("pack", _button_row([self.make_next_button("Skip")]),),
                ("pack", urwid.Divider()),
                ("pack", urwid.Text(msg)),
                ("pack", urwid.Divider()),
                ("pack", _button_row([cal_btn]),),
            ]
        )
        super().__init__(content)


class SetupActivity(api.Activity):
    def __init__(self, shell: api.OpenVarioShell) -> None:
        self.shell = shell

        self._setup_steps(
            [
                WelcomeWizardStep(shell),
                OrientationWizardStep(shell),
                CalibrateTouchWizardStep(shell),
                CalibrateSensorsWizardStep(shell),
            ]
        )

    def create(self) -> urwid.Widget:
        self.content = urwid.Filler(urwid.Padding(urwid.Text("Hello World")))

        self.title = urwid.Text("")
        self.step = urwid.WidgetPlaceholder(urwid.SolidFill(" "))

        self.content_pile = urwid.Pile(
            [("pack", self.title), ("pack", urwid.Divider()), self.step]
        )

        self.frame = urwid.Frame(
            self.content_pile, header=widget.ActivityHeader("Setup wizard"),
        )

        self._switch_step(0)
        return self.frame

    def _setup_steps(self, steps: List[WizardStepWidget]) -> None:
        assert len(steps) > 0
        self._steps = {}
        for n, step_w in enumerate(steps):
            if n + 1 == len(steps):
                next_handler = self._on_wizard_completed
            else:

                def next_handler(w: urwid.Widget, sn=n + 1) -> None:
                    self._switch_step(sn)

            urwid.connect_signal(step_w, "next", next_handler)
            self._steps[n] = step_w
        self._steps = dict(enumerate(steps))

    def _switch_step(self, step_no: int) -> None:
        step_w = self._steps[step_no]
        total_steps = len(self._steps)
        self.title.set_text(
            [f"[{step_no + 1}/{total_steps}] ", ("highlight", f"{step_w.title}")]
        )
        self.step.original_widget = urwid.Filler(step_w, valign="top")
        self.content_pile.set_focus(self.step)
        self.content_pile._selectable = True

    def _on_wizard_completed(self, w: urwid.Widget) -> None:
        done_msg = [
            ("highlight", "Setup is completed"),
            "\n\n",
            "Openvario is ready to use. Happy flying!",
        ]

        exit_btn = widget.PlainButton("Exit")
        urwid.connect_signal(exit_btn, "click", self._on_exit)

        done_contents = [
            (urwid.Text(done_msg), ("pack", None)),
            (urwid.Divider(), ("pack", None)),
            (_button_row([exit_btn]), ("pack", None)),
            (urwid.SolidFill(" "), ("weight", 1)),
        ]
        self.content_pile.contents = done_contents

    def _on_exit(self, w: urwid.Widget) -> None:
        self.shell.screen.pop_activity()


def _button_row(buttons: List[urwid.Widget]) -> urwid.GridFlow:
    return urwid.GridFlow(buttons, 14, 1, 1, "left")