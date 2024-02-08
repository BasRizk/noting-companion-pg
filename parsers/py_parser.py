import os
import ast


# TODO
class PythonParser:
    def __init__(self, path):
        if not os.path.exists(path):
            raise Exception(f'File does not exist: {path}')
        self.path = path
        self.parse()

    def parse(self):
        with open(self.path) as file:
            self.root_node = ast.parse(file.read())

