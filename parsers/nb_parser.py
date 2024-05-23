import json
from copy import deepcopy
from tabulate import tabulate
from textwrap import wrap


class CellEntry:
    def __init__(self, cell_type, cell_id, source, execution_count=None, outputs=None, metadata=None):
        self.cell_type = cell_type
        self.cell_id = cell_id
        self.source = source
        self.execution_count = execution_count
        self.outputs = outputs
        self.metadata = metadata

    def __str__(self):
        return json.dumps({
            'cell_type': self.cell_type,
            'cell_id': self.cell_id,
            'source': self.source,
        }, indent=4)

    def __repr__(self):
        return self.__str__()

    def tabulate(self, text_width=100, compact=True, raw_table=False):
        table = []
        table += [
            ["Cell ID/TYPE", f'{self.cell_id} - {self.cell_type}'],
        ]
        code_wrapped = [wrap(line, width=text_width) for line in self.source]
        for line_num, line in enumerate(code_wrapped):
            for split_num, line_wrap_split in enumerate(line):
                if len(line) > 1:
                    line_id_str = f'Line {line_num + 1}.{split_num + 1}'
                else:
                    line_id_str = f'Line {line_num + 1}'
                table.append([line_id_str, line_wrap_split])

        if not compact:
            if self.execution_count:
                table.append(["Execution Count", self.execution_count])
            if self.outputs:
                table.append(["Outputs", self.outputs])
            if self.metadata:
                table.append(["Metadata", self.metadata])

        if raw_table:
            return table
        else:
            return tabulate(table, tablefmt="fancy_grid", colalign=("right", "left"), stralign="center", numalign="center")


    def get_json(self, compact=True):
        json_data = {
            'cell_type': self.cell_type,
            'id': self.cell_id,
            'source': self.source
        }
        if not compact:
            if self.execution_count:
                json_data['execution_count'] = self.execution_count
            if self.outputs:
                json_data['outputs'] = self.outputs
            if self.metadata:
                json_data['metadata'] = self.metadata
        return json_data

    def __eq__(self, other):
        if isinstance(other, CellEntry):
            for key in self.__dict__.keys():
                if self.__dict__[key] != other.__dict__[key]:
                    return False
            return True
        else:
            return False



class NotebookParser:
    def __init__(self, notebook_filepath):
        self.filepath = notebook_filepath
        with open(self.filepath) as f:
            self.json_data = json.load(f)
        self.parse()

    def __str__(self):
        return json.dumps(
            self.get_cells(json=True, compact=True), indent=4
        )

    def tabulate(self, text_width=100):
        table = []
        for cell in self.get_cells(json=False):
            table += cell.tabulate(raw_table=True, text_width=text_width)
            table.append(['', ''])
        nb_json = tabulate(table, tablefmt="fancy_grid", colalign=("right", "left"), stralign="center", numalign="center")
        return f'Notebook: {self.filepath}\n{nb_json}'


    def __repr__(self):
        return self.__str__()

    def drop_cell(self, cell, copy=True):
        # remove first occurance of cell
        if copy:
            _self = deepcopy(self)
        else:
            _self = self
        _self.cell_entries.remove(cell)
        return _self

    def drop_code(self, cell, copy=True):
        if copy:
            _self = deepcopy(self)
        else:
            _self = self
        for i, line in enumerate(cell.source):
            if line.startswith('#'):
                continue
            else:
                assert _self.cell_entries[cell.cell_id] == cell
                _self.cell_entries[cell.cell_id].source = cell.source[:i]
                break
        return _self

    def drop_content(self, cell, copy=True):
        if copy:
            _self = deepcopy(self)
        else:
            _self = self
        _self.cell_entries[cell.cell_id].source = []
        return _self

    def replace_cell_content(self, cell, log_content, copy=True):
        if copy:
            _self = deepcopy(self)
        else:
            _self = self

        _self.cell_entries[cell.cell_id].source = log_content.split('\\n')
        return _self

    def apply_log_entry(self, cell_id, log_entry, copy=True):
        if copy:
            _self = deepcopy(self)
        else:
            _self = self
        if log_entry.content is None: # NULL log entry
            return _self
        _self.cell_entries[cell_id].source = log_entry.content.split('\\n')

        # ensure that every one ends with '\n' except the last one
        if _self.cell_entries[cell_id].source[0].endswith('\n'):
            # NOTE: it is fake logs, fix up if there are mistakes..
            # fake logs are not supposed to end with '\n'
            while True:
                for i in range(len(_self.cell_entries[cell_id].source) - 1):
                    if not _self.cell_entries[cell_id].source[i].endswith('\n'):
                        # concat the next line to the current line
                        _self.cell_entries[cell_id].source[i] += f'\\n{_self.cell_entries[cell_id].source[i+1]}'
                        _self.cell_entries[cell_id].source.pop(i+1)
                        break
                else:
                    # if not concat has been applied then break, otherwise, test again.
                    break

        return _self

    def find_cell_by_content(self, content, start_from_top=True):
        def _unify_encoding(*strs, encoding='ascii', errors='backslashreplace'):
            # import chardet
            # def _process_str(_s):
            #     # orig_encoding = chardet.detect(_s.encode())['encoding']
            #     # return _s.encode(orig_encoding).decode(encoding, errors).encode(encoding).decode(encoding)
            #     return _s.encode('ascii', 'backslashreplace').strip().decode()
            return [
                _s.encode('ascii', 'backslashreplace').strip().decode()
                for _s in strs
            ]
        _iterator = self.cell_entries if start_from_top else reversed(self.cell_entries)
        for cell in _iterator:
            equal=True
            t1 = cell.source
            t2 = content.split('\\n')
            if len(t1) != len(t2):
                continue
            t1 = map(str.strip, _unify_encoding(*t1))
            t2 = map(str.strip, _unify_encoding(*t2))
            for l1, l2 in zip(t1, t2):
                if l1 != l2:
                    equal=False
                    # breakpoint()
                    break
            if equal:
                return cell
        return None

    def get_cells(self, json=True, compact=True):
        if json:
            cells_json = []
            for cell_entry in self.cell_entries:
                cells_json.append(cell_entry.get_json(compact=compact))
            return cells_json
        else:
            return self.cell_entries

    def parse(self):
        self.cell_entries: CellEntry = []
        cells = self.json_data['cells']
        for i, cell in enumerate(cells):
            cell_id = i # NOTE: rewriting interpretable cell IDs
            cell_type = cell['cell_type']
            source = cell['source']

            executation_count = cell.get('execution_count')
            outputs = cell.get('outputs')
            metadata = cell.get('metadata')
            cell_entry = CellEntry(cell_type, cell_id, source, executation_count, outputs, metadata)
            self.cell_entries.append(cell_entry)
        return self

    def __len__(self):
        return len(self.cell_entries)

    def __getitem__(self, key):
        return self.cell_entries[key]

    def __iter__(self):
        return iter(self.cell_entries)

    def to_notebook(self, directory='__nb_states', filepath_postfix='_modified'):
        cells = self.get_cells(json=True, compact=False)
        for cell, org_cell in zip(cells, self.json_data['cells']):
            if cell['cell_type'] == 'code':
                cell['metadata'] = {}
                cell['outputs'] = []
                cell['id'] = org_cell['id']
            elif cell['cell_type'] == 'markdown':
                cell['metadata'] = {}
            else:
                raise ValueError(f'Unknown cell type: {cell["cell_type"]}')

        update_json = {
            'cells': cells,
            'metadata': self.json_data['metadata'],
            'nbformat': self.json_data['nbformat'],
            'nbformat_minor': self.json_data['nbformat_minor']
        }

        new_filepath = self.filepath.replace('.ipynb', f'{filepath_postfix}.ipynb')
        import os
        if os.path.isabs(new_filepath):
            new_filepath = os.path.relpath(new_filepath)
        new_filepath = f'{directory}/{new_filepath}'
        os.makedirs(os.path.dirname(new_filepath), exist_ok=True)
        with open(new_filepath, 'w') as f:
            json.dump(update_json, f, indent=4)

        return new_filepath

    # def remove_answer_key(self):
    #     # Remove answer key
    #     for i, cell in enumerate(notebook_parser.get_cells()):
    #         if cell['cell_type'] == 'markdown' and cell['source'][0].startswith('# Answer Key'):
    #             break
    #     answer_key_cell_idx = i
    #     # print(f'Answer key cell index: {answer_key_cell_idx}')
    #     # print(f'Content of the answer key cell: {notebook_cells[answer_key_cell_idx]["source"]}')
    #     notebook_cells = notebook_parser[:answer_key_cell_idx]
    #     print('\nAfter removing answer key cell, last cell is:', notebook_parser[-1])

    #     print(f'After removing answer key cell, there are {len(notebook_cells)} cells in the selected notebook')
