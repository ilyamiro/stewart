import logging
from typing import Optional, List
from api.commands.actions import BaseAction, ActionParameters, ActionResult, ExecutionContext, Field

log = logging.getLogger("action: desktop")



class CloseWindowParams(ActionParameters):
    force: bool = Field(default=False, description="Whether to force-kill the window if not responding")


class CloseWindowAction(BaseAction):
    name = "close_window"
    description = "Closes the currently active window using compositor IPC or Alt+F4 fallback."
    parameters_schema = CloseWindowParams
    category = "desktop"
    sample_phrases = ["close window", "close this", "kill window", "exit application"]

    def execute(self, params: CloseWindowParams, ctx: ExecutionContext) -> ActionResult:
        ok = ctx.desktop.close_active_window()
        return ActionResult(success=ok)


class ToggleFloatingParams(ActionParameters):
    pass


class ToggleFloatingAction(BaseAction):
    name = "toggle_floating"
    description = "Toggles floating mode for the currently active window."
    parameters_schema = ToggleFloatingParams
    category = "desktop"
    sample_phrases = ["toggle floating", "make window float", "tile window"]

    def execute(self, params: ToggleFloatingParams, ctx: ExecutionContext) -> ActionResult:
        ok = ctx.desktop.toggle_floating()
        return ActionResult(success=ok)


class ToggleFullscreenParams(ActionParameters):
    pass


class ToggleFullscreenAction(BaseAction):
    name = "toggle_fullscreen"
    description = "Toggles fullscreen mode for the active window."
    parameters_schema = ToggleFullscreenParams
    category = "desktop"
    sample_phrases = ["fullscreen", "toggle fullscreen", "maximize window"]

    def execute(self, params: ToggleFullscreenParams, ctx: ExecutionContext) -> ActionResult:
        ok = ctx.desktop.toggle_fullscreen()
        return ActionResult(success=ok)


class MoveWindowToMonitorParams(ActionParameters):
    direction: str = Field(default="next", description="Monitor direction to move the active window ('next', 'previous', 'right', 'left')")


class MoveWindowToMonitorAction(BaseAction):
    name = "move_window_to_monitor"
    description = "Moves the active window to the next or previous monitor display."
    parameters_schema = MoveWindowToMonitorParams
    category = "desktop"
    sample_phrases = ["move window to next monitor", "switch display", "move to right monitor"]

    def execute(self, params: MoveWindowToMonitorParams, ctx: ExecutionContext) -> ActionResult:
        ok = ctx.desktop.move_window_to_monitor(params.direction)
        return ActionResult(success=ok)



class SwitchWorkspaceParams(ActionParameters):
    workspace: Optional[str] = Field(default=None, description="Workspace number, name, or direction (e.g. '1', '2', '+1', '-1')")
    context: Optional[str] = Field(default="", description="Speech context to extract workspace from")


class SwitchWorkspaceAction(BaseAction):
    name = "switch_workspace"
    description = "Switches desktop viewport to the specified workspace."
    parameters_schema = SwitchWorkspaceParams
    category = "desktop"
    sample_phrases = ["switch to workspace 2", "go to workspace one", "next workspace"]
    requires_context = True

    def execute(self, params: SwitchWorkspaceParams, ctx: ExecutionContext) -> ActionResult:
        ws = params.workspace
        if not ws:
            ws = ctx.desktop.extract_workspace(params.context or ctx.context)
        else:
            ws = str(ws)

        ok = ctx.desktop.switch_workspace(ws)
        return ActionResult(success=ok, data={"workspace": ws})


class MoveToWorkspaceParams(ActionParameters):
    workspace: Optional[str] = Field(default=None, description="Workspace number, name, or direction (e.g. '1', '2', '+1')")
    context: Optional[str] = Field(default="", description="Speech context to extract workspace from")


class MoveToWorkspaceAction(BaseAction):
    name = "move_to_workspace"
    description = "Moves the active window to the specified workspace."
    parameters_schema = MoveToWorkspaceParams
    category = "desktop"
    sample_phrases = ["move window to workspace 3", "send to workspace 2"]
    requires_context = True

    def execute(self, params: MoveToWorkspaceParams, ctx: ExecutionContext) -> ActionResult:
        ws = params.workspace
        if not ws:
            ws = ctx.desktop.extract_workspace(params.context or ctx.context)
        else:
            ws = str(ws)

        ok = ctx.desktop.move_to_workspace(ws)
        return ActionResult(success=ok, data={"workspace": ws})



class SerpWidgetParams(ActionParameters):
    widget: str = Field(default="launcher", description="Name of shell widget to toggle ('launcher', 'clipboard', 'music', 'calendar', 'volume', 'network', 'system', 'wallpaper', 'guide')")


class SerpWidgetAction(BaseAction):
    name = "serp_widget"
    description = "Toggles a Serpantinum desktop shell widget."
    parameters_schema = SerpWidgetParams
    category = "desktop"
    sample_phrases = ["open app launcher", "toggle clipboard", "show calendar widget"]

    def execute(self, params: SerpWidgetParams, ctx: ExecutionContext) -> ActionResult:
        ok = ctx.desktop.toggle_widget(params.widget)
        return ActionResult(success=ok)


class SerpReloadParams(ActionParameters):
    pass


class SerpReloadAction(BaseAction):
    name = "serp_reload"
    description = "Reloads the desktop shell / Serpantinum user interface."
    parameters_schema = SerpReloadParams
    category = "desktop"
    sample_phrases = ["reload shell", "restart desktop shell"]

    def execute(self, params: SerpReloadParams, ctx: ExecutionContext) -> ActionResult:
        ok = ctx.desktop.reload_shell()
        return ActionResult(success=ok)


class ScreenshotParams(ActionParameters):
    mode: str = Field(default="area", description="Screenshot capture mode ('area' for interactive selection, 'full' for full screen)")


class ScreenshotAction(BaseAction):
    name = "screenshot"
    description = "Captures a screenshot (full screen or selected area) and copies it to clipboard."
    parameters_schema = ScreenshotParams
    category = "desktop"
    sample_phrases = ["take a screenshot", "capture screen", "screenshot area"]

    def execute(self, params: ScreenshotParams, ctx: ExecutionContext) -> ActionResult:
        ok = ctx.desktop.screenshot(params.mode)
        return ActionResult(success=ok)


class LockSessionParams(ActionParameters):
    pass


class LockSessionAction(BaseAction):
    name = "lock_session"
    description = "Locks the active user session cleanly."
    parameters_schema = LockSessionParams
    category = "desktop"
    sample_phrases = ["lock session", "lock screen", "lock computer"]

    def execute(self, params: LockSessionParams, ctx: ExecutionContext) -> ActionResult:
        ok = ctx.desktop.lock_session()
        return ActionResult(success=ok)


class MediaControlParams(ActionParameters):
    control: str = Field(default="play-pause", description="Media playback command ('play-pause', 'play', 'pause', 'next', 'previous', 'stop')")


class MediaControlAction(BaseAction):
    name = "media_control"
    description = "Controls media playback across active desktop media players via playerctl."
    parameters_schema = MediaControlParams
    category = "media"
    sample_phrases = ["pause music", "resume video", "next track", "skip song"]

    def execute(self, params: MediaControlParams, ctx: ExecutionContext) -> ActionResult:
        ok = ctx.desktop.media_control(params.control)
        return ActionResult(success=ok)


close_window = CloseWindowAction()
toggle_floating = ToggleFloatingAction()
toggle_fullscreen = ToggleFullscreenAction()
move_window_to_monitor = MoveWindowToMonitorAction()
switch_workspace = SwitchWorkspaceAction()
move_to_workspace = MoveToWorkspaceAction()
serp_widget = SerpWidgetAction()
serp_reload = SerpReloadAction()
screenshot = ScreenshotAction()
lock_session = LockSessionAction()
media_control = MediaControlAction()
