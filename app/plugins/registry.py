from typing import List, Dict, Any
from app.plugins.base import BaseAnalyzerPlugin

class PluginRegistry:
    def __init__(self):
        self._plugins: List[BaseAnalyzerPlugin] = []

    def register(self, plugin: BaseAnalyzerPlugin):
        """Register a plugin to the pipeline sequentially."""
        if any(p.name == plugin.name for p in self._plugins):
            return
        self._plugins.append(plugin)

    def get_plugins(self) -> List[BaseAnalyzerPlugin]:
        return self._plugins

    def run_pipeline(self, repo_path: str, initial_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Runs each plugin in order and accumulates results into context."""
        context = initial_context or {}
        context["repo_path"] = repo_path
        
        for plugin in self._plugins:
            try:
                # Plugins may inspect context to reuse results of previous steps
                result = plugin.analyze(repo_path, context)
                context[plugin.name] = result
            except Exception as e:
                # Mark execution details on failure
                raise ValueError(f"Plugin '{plugin.name}' analysis failed: {str(e)}")
        
        return context

plugin_registry = PluginRegistry()
