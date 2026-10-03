import ast


class FunctionCallVisitor(ast.NodeVisitor):
    def __init__(self, target_function_name):
        self.target_function_name = target_function_name
        self.is_called = False

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and node.func.id == self.target_function_name:
            self.is_called = True
        self.generic_visit(node)


class MonitoredVariable:
    def __init__(self, initial_value=None, callback=None):
        self._value = initial_value
        self._callback = callback

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, new_value):
        if self._callback:
            self._callback(new_value)  # Call the callback when value changes
        self._value = new_value

    def set_callback(self, new_callback):
        self._callback = new_callback


class ValueTracker:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ValueTracker, cls).__new__(cls)
            cls._instance.value = [None, ]
        return cls._instance

    def set_value(self, text):
        if len(self.value) == 2:
            self.value.pop(0)
        self.value.append(text)

    def get_value(self):
        return self.value[-1]

    def reset(self):
        self.value = [None, ]


tracker = ValueTracker()