import json
from typing import List, Tuple
from copy import deepcopy
from tabulate import tabulate
from textwrap import wrap

def _reformat_code_lines(_source):
    if len(_source) == 0:
        return []
    source = [
        line
        # line.rstrip() # remove trailing whitespace
        for line in _source
        if line.strip() # keep only non-empty lines
    ]
    comment_lines = []
    comment_following_lines = []
    for i, line in enumerate(source):
        if line.startswith('#'):
            prev_line = None if i == 0 else source[i-1]
            comment_lines.append(line)
            comment_following_lines.append(prev_line)

    code = '\n'.join(list(map(str.rstrip, _source)))

    def _parse_code(code):
        # import black
        # mode=black.Mode()
        # longest_line_in_code = max([len(line)*2 for line in code.split('\n')])
        # mode.line_length = longest_line_in_code
        # formatted_code = black.format_str(code, mode=mode)
        # return formatted_code

        # Parse the code into an Abstract Syntax Tree (AST)
        import ast
        import astunparse
        tree = ast.parse(code, type_comments=True)

        # Unparse the AST back into code
        formatted_code = astunparse.unparse(tree)

        code = formatted_code.strip()
        return code


    new_source = _parse_code(code).split('\n')

    # drop comments that were kept by the parser from the leftover comments
    kept_comments = []
    kept_following_lines = []
    for comment, following_line in zip(comment_lines, comment_following_lines):
        if comment.strip() not in new_source:
            kept_comments.append(comment)
            kept_following_lines.append(following_line)
    comment_lines = kept_comments

    new_source = [line.rstrip() for line in new_source if line.strip()]

    _comment_following_lines = comment_following_lines
    comment_following_lines = []
    for line in _comment_following_lines:
        if line:
            line = line.strip()
            try:
                _line = _parse_code(line)
                if _line:
                    line = _line
            except Exception:
                pass

        comment_following_lines.append(line)
    del _comment_following_lines

    # verification step
    for line in comment_following_lines:
        if line == '':
            raise ValueError('Comment following line is empty and not None!')


    # add back the comments
    for comment, following_line in zip(comment_lines, comment_following_lines):
        if following_line:
            # new_source.insert(code_lines.index(following_line) + 1, comment)
            for i, line in enumerate(new_source):
                if line.rstrip().endswith(following_line.strip()):
                    new_source.insert(i + 1, comment)
                    break
            else:
                breakpoint()
                raise ValueError(f'Could not find the following line: {following_line}')
        else:
            new_source.insert(0, comment)

    new_source = [line.rstrip() for line in new_source if line.strip()]
    return new_source


class CellEntry:
    def __init__(self, cell_type, cell_id, source, execution_count=None, outputs=None, metadata=None):
        self.cell_type = cell_type
        self.cell_id = cell_id
        self._source = source
        self._tokenized_source = _reformat_code_lines(source)
        self.execution_count = execution_count
        self.outputs = outputs
        self.metadata = metadata

    @property
    def source(self):
        return self._tokenized_source

    @source.setter
    def source(self, v):
        if not isinstance(v, list):
            raise ValueError(f'Expected list, got {type(v)}')
        self._source = v
        self._tokenized_source = _reformat_code_lines(v)

    def __str__(self):
        return json.dumps({
            'cell_type': self.cell_type,
            'cell_id': self.cell_id,
            'source': self.source,
        }, indent=4)

    def __repr__(self):
        return self.__str__()

    def tabulate(self, text_width=100, compact=True, raw_table=False):
        breakpoint()
        table = []
        table += [
            ["Cell ID/TYPE", f'{self.cell_id} - {self.cell_type}'],
        ]
        code_wrapped = [wrap(line, width=text_width) for line in self._source] # NOTE: this is the raw form of the source
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

    def get_json(self, compact=True, tokenize=True):
        if tokenize:
            source = self._tokenized_source
        else:
            source = self._source

        json_data = {
            'cell_type': self.cell_type,
            'id': self.cell_id,
            'source': source
        }

        if not compact:
            if self.execution_count:
                json_data['execution_count'] = self.execution_count
            if self.outputs:
                json_data['outputs'] = self.outputs
            if self.metadata:
                json_data['metadata'] = self.metadata
        return json_data

    def get_xml(self, compact=True, tokenize=True):
        if tokenize:
            source = self._tokenized_source
        else:
            source = self._source

        xml_data = f'<cell>\n'
        xml_data += f'<cell_type>{self.cell_type}</cell_type>\n'
        xml_data += f'<id>{self.cell_id}</id>\n'
        xml_data += f'<source>\n'
        for line in source:
            xml_data += f'{line}\n'
        xml_data += f'</source>\n'
        if not compact:
            if self.execution_count:
                xml_data += f'<execution_count>{self.execution_count}</execution_count>\n'
            if self.outputs:
                xml_data += f'<outputs>{self.outputs}</outputs>\n'
            if self.metadata:
                xml_data += f'<metadata>{self.metadata}</metadata>\n'
        xml_data += f'</cell>\n'
        return xml_data

    def __eq__(self, other):
        if isinstance(other, CellEntry):
            for key in self.__dict__.keys():
                # ignore _source that as long as the tokenized source is the same
                if self.__dict__[key] != other.__dict__[key] and key != '_source':
                    return False
                if self.source != other.source:
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

    def tabulate(self, text_width=100) -> str:
        table = []
        for cell in self.get_cells(json=False):
            table += cell.tabulate(raw_table=True, text_width=text_width)
            table.append(['', ''])
        nb_json = tabulate(table, tablefmt="fancy_grid", colalign=("right", "left"), stralign="center", numalign="center")
        return f'Notebook: {self.filepath}\n{nb_json}'

    def get_diff(self, other) -> List[Tuple[CellEntry, CellEntry]]:
        # get the differing cells entries
        diff_cells = []
        for cell, other_cell in zip(self.cell_entries, other.cell_entries):
            if cell != other_cell:
                diff_cells.append((cell, other_cell))
        return diff_cells

    def get_updates(self, other) -> List[CellEntry]:
        diffs = self.get_diff(other)
        return [diff[1] for diff in diffs]

    def __repr__(self):
        return self.__str__()

    def drop_cell(self, cell, copy=True) -> 'NotebookParser':
        # remove first occurance of cell
        if copy:
            _self = deepcopy(self)
        else:
            _self = self
        _self.cell_entries.remove(cell)
        return _self

    def drop_code(self, cell: CellEntry, copy: bool=True) -> 'NotebookParser':
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

    def drop_content(self, cell: CellEntry, copy: bool=True) -> 'NotebookParser':
        if copy:
            _self = deepcopy(self)
        else:
            _self = self
        # TODO ensure that the content is the same
        if _self.cell_entries[cell.cell_id].source != cell.source:
            breakpoint()
            raise ValueError('Content is not the same')
        _self.cell_entries[cell.cell_id].source = []
        return _self

    def replace_cell_content(self, cell, log_content, copy=True) -> 'NotebookParser':
        if copy:
            _self = deepcopy(self)
        else:
            _self = self

        _self.cell_entries[cell.cell_id].source = log_content.split('\\n')
        return _self

    def apply_log_entry(self, cell_id, log_entry, copy=True) -> 'NotebookParser':
        if copy:
            _self = deepcopy(self)
        else:
            _self = self
        if log_entry.content is None: # NULL log entry
            return _self

        if not log_entry.content:
            raise ValueError('Log entry content is empty')

        _self.cell_entries[cell_id].source = log_entry.content.split('\n')

        # if _self.cell_entries[cell_id].source == ['']:
        #     breakpoint()
        #     _self.cell_entries[cell_id].source = []

        # # ensure that every one ends with '\n' except the last one
        # if _self.cell_entries[cell_id].source[0].endswith('\n'):
        #     # NOTE: it is fake logs, fix up if there are mistakes..
        #     # fake logs are not supposed to end with '\n'
        #     while True:
        #         for i in range(len(_self.cell_entries[cell_id].source) - 1):
        #             if not _self.cell_entries[cell_id].source[i].endswith('\n'):
        #                 # concat the next line to the current line
        #                 _self.cell_entries[cell_id].source[i] += f'\\n{_self.cell_entries[cell_id].source[i+1]}'
        #                 _self.cell_entries[cell_id].source.pop(i+1)
        #                 break
        #         else:
        #             # if not concat has been applied then break, otherwise, test again.
        #             break

        return _self

    def find_cell_by_content(self, content, start_from_top=True) -> CellEntry:
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

    def get_cells(self, json=True, compact=True) -> List[CellEntry]:
        if json:
            cells_json = []
            for cell_entry in self.cell_entries:
                cells_json.append(cell_entry.get_json(compact=compact))
            return cells_json
        else:
            return self.cell_entries

    def parse(self) -> 'NotebookParser':
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

    def to_notebook(self, directory='__nb_states', filepath_postfix='_modified') -> str:
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
