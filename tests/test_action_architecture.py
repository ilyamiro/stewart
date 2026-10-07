import sys
import json
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from api.services.desktop import DesktopService, get_desktop_service
from api.commands.actions import BaseAction, ActionParameters, ActionResult, ExecutionContext, Field
from api.commands.tools import ActionTool, ToolRegistry
from api.commands.tree import Command
import plugins.core.actions.desktop as desktop_actions
import plugins.core.actions.core as core_actions


class TestDesktopService(unittest.TestCase):
    def setUp(self):
        self.service = DesktopService()

    def test_compositor_detection(self):
        comp = self.service.get_compositor()
        self.assertIn(comp, ["hyprland", "niri", "sway", "other"])

    def test_extract_workspace_digits(self):
        self.assertEqual(self.service.extract_workspace("switch to 4"), "4")

    def test_extract_workspace_words2num(self):
        self.assertEqual(self.service.extract_workspace("go to workspace three"), "3")
        self.assertEqual(self.service.extract_workspace("move to seven"), "7")

    def test_extract_workspace_fallback(self):
        self.assertEqual(self.service.extract_workspace("next workspace"), "+1")


class TestActionsAndToolCalling(unittest.TestCase):
    def test_desktop_actions_schemas(self):
        actions = [
            desktop_actions.close_window,
            desktop_actions.toggle_floating,
            desktop_actions.toggle_fullscreen,
            desktop_actions.move_window_to_monitor,
            desktop_actions.switch_workspace,
            desktop_actions.move_to_workspace,
            desktop_actions.serp_widget,
            desktop_actions.serp_reload,
            desktop_actions.screenshot,
            desktop_actions.lock_session,
            desktop_actions.media_control,
        ]

        for action in actions:
            self.assertIsInstance(action, BaseAction)
            tool_def = action.to_ollama_tool()
            self.assertEqual(tool_def["type"], "function")
            fn = tool_def["function"]
            self.assertEqual(fn["name"], action.name)
            self.assertTrue(len(fn["description"]) > 0)
            self.assertIn("parameters", fn)
            self.assertEqual(fn["parameters"]["type"], "object")
            json_str = json.dumps(tool_def)
            self.assertTrue(len(json_str) > 0)

    def test_core_actions_schemas(self):
        actions = [
            core_actions.typing,
            core_actions.subprocess,
            core_actions.click,
            core_actions.hotkey,
            core_actions.key,
            core_actions.scroll,
            core_actions.browser,
        ]

        for action in actions:
            self.assertIsInstance(action, BaseAction)
            tool_def = action.to_ollama_tool()
            self.assertEqual(tool_def["type"], "function")
            fn = tool_def["function"]
            self.assertEqual(fn["name"], action.name)
            self.assertTrue(len(fn["description"]) > 0)
            self.assertIn("parameters", fn)

    def test_action_execution_via_callable(self):
        cmd = Command(
            keywords=["close", "tab"],
            action="hotkey",
            parameters={"hotkey": ["ctrl", "w"]}
        )
        res = core_actions.hotkey(command=cmd)
        self.assertIsInstance(res, ActionResult)
        self.assertTrue(res.success)

    def test_switch_workspace_execution(self):
        cmd = Command(
            keywords=["workspace"],
            action="switch_workspace",
            parameters={"workspace": "2"}
        )
        res = desktop_actions.switch_workspace(command=cmd)
        self.assertIsInstance(res, ActionResult)
        self.assertEqual(res.data.get("workspace"), "2")

    def test_tool_registry_integration(self):
        registry = ToolRegistry()
        mock_api = type("MockAPI", (), {
            "__actions__": {
                "close_window": desktop_actions.close_window,
                "hotkey": core_actions.hotkey,
                "legacy_func": lambda **kwargs: "ok"
            },
            "config": {
                "commands": {
                    "default": [
                        {
                            "action": "close_window",
                            "command": ["close", "window"],
                            "equivalents": [["kill", "window"]]
                        }
                    ]
                }
            }
        })()

        registry.sync_from_app(mock_api)
        self.assertIn("close_window", registry.get_tool_names())
        self.assertIn("hotkey", registry.get_tool_names())
        self.assertIn("legacy_func", registry.get_tool_names())

        schemas = registry.get_all_tool_schemas()
        self.assertGreaterEqual(len(schemas), 3)

        tool_res = registry.execute("hotkey", parameters={"hotkey": ["ctrl", "t"]})
        self.assertIsInstance(tool_res, ActionResult)
        self.assertTrue(tool_res.success)


if __name__ == "__main__":
    unittest.main()
