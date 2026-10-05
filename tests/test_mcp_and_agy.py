"""
Unit tests for Stewart MCP Tool Integration & Agy Caller.
Tests:
1. MCPManager configuration and tool discovery for studieplus and gmail.
2. ToolRegistry synchronization with MCP tools and Ollama/Qwen schema generation.
3. AgyCaller text sanitization for clean Kokoro TTS speech.
4. CommandRouter routing with mode='agy' and provider='agy'.
"""
import sys
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from api.commands.mcp_client import MCPManager, KNOWN_MCP_TOOLS
from api.commands.tools import ToolRegistry, ActionTool
from api.commands.agy_caller import AgyCaller
from api.commands.tree import Command, Manager
from api.commands.router import CommandRouter


class TestMCPIntegration(unittest.TestCase):
    def setUp(self):
        self.manager = MCPManager({
            "mcp": {
                "enabled": True,
                "servers": {
                    "studieplus": {"command": "/home/ilyamiro/Projects/life/bin/studieplus-mcp"},
                    "gmail": {"command": "/home/ilyamiro/Projects/life/bin/gmail-mcp"}
                }
            }
        })

    def tearDown(self):
        self.manager.close()


    def test_discover_tools(self):
        tools = self.manager.discover_tools()
        self.assertGreater(len(tools), 0)
        tool_names = [t["name"] for t in tools]

        # Verify Studieplus tools
        self.assertIn("studieplus_get_schedule", tool_names)
        self.assertIn("studieplus_get_assignments", tool_names)
        self.assertIn("study_get_ib_resources", tool_names)
        self.assertIn("study_prepare_test", tool_names)

        # Verify Gmail tools
        self.assertIn("gmail_check_status", tool_names)
        self.assertIn("gmail_search_emails", tool_names)
        self.assertIn("gmail_send_email", tool_names)

    def test_tool_registry_mcp_sync(self):
        registry = ToolRegistry(mcp_manager=self.manager)
        registry.sync_from_mcp()

        tools = registry.list_tools()
        names = registry.get_tool_names()

        self.assertIn("studieplus_get_schedule", names)
        self.assertIn("gmail_search_emails", names)

        # Check tool properties
        tool = registry.get("studieplus_get_schedule")
        self.assertIsNotNone(tool)
        self.assertTrue(getattr(tool, "is_query", False))
        self.assertEqual(tool.plugin_name, "mcp:studieplus")

        # Verify schema export for Qwen / Ollama
        schemas = registry.get_all_tool_schemas()
        schema_names = [s["function"]["name"] for s in schemas]
        self.assertIn("studieplus_get_schedule", schema_names)
        self.assertIn("gmail_search_emails", schema_names)


class TestAgyCaller(unittest.TestCase):
    def setUp(self):
        self.caller = AgyCaller(skill_name="stewart-voice")

    def test_clean_text_for_tts(self):
        raw_markdown = (
            "### Hello there!\n\n"
            "Here is your **schedule** for *today*:\n"
            "- 10:15: Mathematics AA HL in room 204\n"
            "- 12:00: Physics HL 🔬\n\n"
            "```python\nprint('code block')\n```\n"
            "Have a great day! 😊"
        )
        cleaned = self.caller.clean_text_for_tts(raw_markdown)

        # Ensure all markdown and emojis are stripped
        self.assertNotIn("###", cleaned)
        self.assertNotIn("**", cleaned)
        self.assertNotIn("*", cleaned)
        self.assertNotIn("-", cleaned)
        self.assertNotIn("```", cleaned)
        self.assertNotIn("print('code block')", cleaned)
        self.assertNotIn("🔬", cleaned)
        self.assertNotIn("😊", cleaned)
        self.assertIn("Hello there!", cleaned)
        self.assertIn("Mathematics AA HL in room 204", cleaned)


class TestRouterAgyIntegration(unittest.TestCase):
    def setUp(self):
        self.manager = Manager()
        self.registry = ToolRegistry()
        self.router = CommandRouter(
            self.manager,
            self.registry,
            config={
                "router": {
                    "mode": "agy",
                    "agy": {"command": "echo", "skill_name": None}
                }
            }
        )

    def test_router_mode_agy(self):
        # Mock agy caller to return plain text
        from api.commands.agy_caller import AgyResponse
        self.router.agy_caller.execute_request = lambda req, confirmed=False: AgyResponse(f"Mock voice response to {req}")
        results = self.router.route("what is my schedule")

        self.assertEqual(len(results), 1)
        cmd, ctx = results[0]
        self.assertEqual(cmd.action, "speak")
        self.assertTrue(cmd.tts)
        self.assertEqual(cmd.parameters.get("text"), "Mock voice response to what is my schedule")

    def test_router_persona_provider_agy(self):
        from api.commands.agy_caller import AgyResponse
        self.assertEqual(self.router.persona_provider, "agy")
        self.assertIsNone(self.router.persona_caller)

        self.router.agy_caller.execute_request = lambda prompt, confirmed=False: AgyResponse("Very good, Sir. The volume has been adjusted.")
        resp = self.router.generate_persona_response(
            user_query="turn up the volume",
            tool_name="volume",
            tool_result={"status": "success", "level": 80}
        )
        self.assertEqual(resp, "Very good, Sir. The volume has been adjusted.")

    def test_router_persona_stream_agy(self):
        from api.commands.agy_caller import AgyResponse
        self.router.agy_caller.execute_request = lambda prompt, confirmed=False: AgyResponse("Right away, Sir.")
        stream = list(self.router.stream_persona_response(
            user_query="hello",
            lang="en"
        ))
        self.assertEqual(stream, ["Right away, Sir."])


class TestDynamicTools(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.temp_file = Path(tempfile.mktemp(suffix=".json"))
        from api.commands.dynamic_tools import DynamicToolManager
        self.mgr = DynamicToolManager(storage_file=self.temp_file)

    def tearDown(self):
        if self.temp_file.exists():
            self.temp_file.unlink()

    def test_register_and_execute(self):
        tool = self.mgr.register(
            name="echo_test",
            description="Echo a message",
            command_template="echo hello {name}",
            parameters_schema={"type": "object", "properties": {"name": {"type": "string"}}},
            sample_phrases=["say hello to"]
        )
        self.assertEqual(tool.name, "echo_test")
        
        # Test execution
        res = tool.execute(name="Illia")
        self.assertTrue(res["success"])
        self.assertEqual(res["stdout"], "hello Illia")

        # Test reload from file
        from api.commands.dynamic_tools import DynamicToolManager
        reloaded_mgr = DynamicToolManager(storage_file=self.temp_file)
        loaded_tool = reloaded_mgr.get("echo_test")
        self.assertIsNotNone(loaded_tool)
        self.assertEqual(loaded_tool.command_template, "echo hello {name}")

    def test_registry_integration(self):
        from api.commands.dynamic_tools import DynamicToolManager
        self.mgr.register(
            name="rename_file",
            description="Rename a file",
            command_template="mv {src} {dst}",
            parameters_schema={"type": "object", "properties": {"src": {"type": "string"}, "dst": {"type": "string"}}},
            sample_phrases=["rename file"]
        )
        registry = ToolRegistry()
        # Patch dynamic tool manager singleton in registry sync
        import api.commands.dynamic_tools as dt_mod
        orig = dt_mod._dynamic_tool_manager
        dt_mod._dynamic_tool_manager = self.mgr
        try:
            registry.sync_dynamic_tools()
            tool = registry.get("rename_file")
            self.assertIsNotNone(tool)
            self.assertEqual(tool.plugin_name, "dynamic")
            self.assertTrue(tool.is_query)
        finally:
            dt_mod._dynamic_tool_manager = orig


class TestVoiceConfirmation(unittest.TestCase):
    def test_confirmation_detection(self):
        caller = AgyCaller(skill_name="stewart-voice")
        raw_text = "CONFIRMATION_REQUIRED: Sir, deleting notes.txt is irreversible. Would you like me to proceed?"
        
        # Test confirmation parsing
        import re
        conf_match = re.search(r"CONFIRMATION_REQUIRED:\s*(.*)", raw_text, re.IGNORECASE)
        self.assertTrue(bool(conf_match))
        prompt = caller.clean_text_for_tts(conf_match.group(1))
        self.assertIn("deleting notes.txt", prompt)

    def test_router_confirmation_action(self):
        from api.commands.agy_caller import AgyResponse
        manager = Manager()
        registry = ToolRegistry()
        router = CommandRouter(
            manager,
            registry,
            config={"router": {"mode": "agy"}}
        )
        # Mock agy caller returning a confirmation required response
        router.agy_caller.execute_request = lambda req, confirmed=False: AgyResponse(
            "Sir, deleting this requires confirmation.",
            needs_confirmation=True,
            confirmation_prompt="Sir, deleting this requires confirmation."
        )
        results = router.route("delete old files")
        self.assertEqual(len(results), 1)
        cmd, ctx = results[0]
        self.assertEqual(cmd.action, "confirmation")
        self.assertTrue(cmd.needs_confirmation)
        self.assertEqual(cmd.parameters["prompt"], "Sir, deleting this requires confirmation.")


if __name__ == "__main__":
    unittest.main()

