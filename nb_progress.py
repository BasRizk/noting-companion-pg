import textwrap
from parsers.nb_parser import NotebookParser
from parsers.log_parser import LogParser, LogEntry
from utils import logger

class NBStep:
    def __init__(self,
                 nb_parser_state: NotebookParser,
                 log_entry: LogEntry=None,
                 cell_id: int=None,
                 change_type: str=None):
        if not isinstance(nb_parser_state, NotebookParser):
            raise Exception(f'Invalid nb_parser_state type: {type(nb_parser_state)}')

        if not (log_entry is None or isinstance(log_entry, LogEntry)):
            raise Exception(f'Invalid log_entry type: {type(log_entry)}')

        self.entries = [] if log_entry is None else [log_entry]
        self.change_type = [] if change_type is None else [change_type]
        self.cell_id = cell_id
        self.nb_parser_state = nb_parser_state
        self.idx = -1
        self._verify()

    def _verify(self):
        _case_1 = (self.cell_id is None and len(self.entries) == 0)
        _case_2 = (len(self.entries) > 0 and self.cell_id is not None)
        return _case_1 or _case_2

    def get_change_type(self, change_i):
        if change_i > 0:
            raise NotImplementedError("not implemented for change_i > 0")
        return self.change_type[change_i]
        # if change_i == 0:
        #     return 'INSERT'
        # else:
        #     return 'UPDATE'

    def __len__(self):
        return len(self.entries)

    def __iter__(self):
        return self

    def __next__(self):
        self.idx += 1
        if self.idx >= len(self.entries):
            raise StopIteration
        return self.nb_parser_state.apply_log_entry(self.cell_id, self.entries[self.idx])

    def reset(self):
        self.idx = -1

    # def add_prev_entries(self, prev_log_entries):
    #     if not isinstance(prev_log_entries, list):
    #         prev_log_entries = [prev_log_entries]
    #     self.entries = prev_log_entries + self.entries

    def __str__(self):
        entry_content_pp = textwrap.indent('\n'.join(self.entries[-1].content.split('\\n')), '    ') if self.entries else "None"
        if self.entries:
            prev_entries_pp = [textwrap.indent('\n'.join(entry.content.split('\\n')), '    ') for entry in self.entries[:-1]]
            prev_entries_pp = '\n'.join(prev_entries_pp)
        else:
            prev_entries_pp = "None"

        return f"{'='*80}\n" +\
            f"Prev entries:\n{prev_entries_pp}\n\n" +\
            f"Log entry @ cell_id {self.cell_id}:\n{entry_content_pp}\n\n" +\
            f"Notebook State:\n{self.nb_parser_state}\n" +\
            f"{'='*80}"

    def __repr__(self):
        return self.__str__()

    def generate_next_step(self, selected_log_entry, start_from_top=True, replacement_log_entry=None):
        found_cell = self.nb_parser_state.find_cell_by_content(selected_log_entry.content, start_from_top=start_from_top)
        if found_cell:
            if replacement_log_entry.content is not None:
                new_state = self.nb_parser_state.replace_cell_content(found_cell, replacement_log_entry.content)
                # add type of change
                # if a line is added    :  INSERT
                if len(found_cell.source) < len(replacement_log_entry.content.split('\\n')):
                    change_type = 'INSERT'
                # if a line is removed  :  DELETE
                elif len(found_cell.source) > len(replacement_log_entry.content.split('\\n')):
                    change_type = 'DELETE'
                # if both have the same number of lines: UPDATE
                elif len(found_cell.source) == len(replacement_log_entry.content.split('\\n')):
                    change_type = 'UPDATE'
                else:
                    raise Exception('Invalid change type')
            else:
                # new_state = self.nb_parser_state.drop_code(found_cell)
                raise NotImplementedError()

            if new_state is None:
                raise Exception(f'Failed to apply log entry to notebook state:\n{log_entry}\n{self.nb_parser_state}')

            next_step = NBStep(
                nb_parser_state=new_state,
                log_entry=replacement_log_entry,
                cell_id=found_cell.cell_id,
                change_type=change_type
            )
            return next_step
        return None

from parsers.nb_parser import NotebookParser
from parsers.log_parser import LogParser

class InvalidLogError(Exception):
    pass

class NotebookStateLogMismatchError(Exception):
    pass

def get_notebook_progress_using_log(nb_parser: NotebookParser, nb_log_parser: LogParser, verbose=0):
    nb_progress = [NBStep(nb_parser)]

    # reversed_nb_log_parser = reversed(nb_log_parser)
    log_entry_idx_ptr = 0
    while log_entry_idx_ptr < len(nb_log_parser):
        if nb_log_parser[log_entry_idx_ptr].entry_type == "CELL_EXECUTION_END":
            ckpt_ptr = log_entry_idx_ptr # checkpoint

            if nb_log_parser[log_entry_idx_ptr].cell_type != "code":
                raise InvalidLogError(f'Non-code CELL_EXECUTION_END cell encountered:\n{nb_log_parser[log_entry_idx_ptr]}')

            logger.trace(f'Found CELL_EXECUTION_END entry @ {log_entry_idx_ptr}')
            # logger.trace(f'{nb_log_parser[log_entry_idx_ptr]}')

            cell_excution_end_entry = nb_log_parser[log_entry_idx_ptr]

            # find the corresponding CELL_EXECUTION_BEGIN entry
            while log_entry_idx_ptr > 0 and nb_log_parser[log_entry_idx_ptr].entry_type != "CELL_EXECUTION_BEGIN":
                log_entry_idx_ptr -= 1
            if log_entry_idx_ptr < 0 or nb_log_parser[log_entry_idx_ptr].entry_type != "CELL_EXECUTION_BEGIN":
                raise InvalidLogError('Failed to find CELL_EXECUTION_END `CELL_EXECUTION_BEGIN` entry')
            cell_excution_begin_entry = nb_log_parser[log_entry_idx_ptr]

            if cell_excution_begin_entry.cell_type != "code":
                raise InvalidLogError(f'Non-code CELL_EXECUTION_BEGIN cell encountered:\n{cell_excution_begin_entry}')

            if cell_excution_begin_entry.content != cell_excution_end_entry.content:
                raise InvalidLogError(
                    f'CELL_EXECUTION_BEGIN and CELL_EXECUTION_END content mismatch @ line {log_entry_idx_ptr} in file {nb_log_parser.filepath}:\n\n'
                    f'{cell_excution_begin_entry}\n\n'
                    f'{cell_excution_end_entry}\n\n'
                )


            logger.trace(f'Found CELL_EXECUTION_BEGIN entry @ {log_entry_idx_ptr}')
            # logger.trace(f'{nb_log_parser[log_entry_idx_ptr]}')

            # find the previous CELL_SELECTED entry
            while log_entry_idx_ptr > 0 and nb_log_parser[log_entry_idx_ptr].entry_type != "CELL_SELECTED":
                log_entry_idx_ptr -= 1
            cell_selected_entry = nb_log_parser[log_entry_idx_ptr]
            if log_entry_idx_ptr < 0 or cell_selected_entry.entry_type != "CELL_SELECTED":
                raise InvalidLogError('Failed to find corresponding CELL_SELECTED entry')

            if cell_selected_entry.cell_type != cell_excution_begin_entry.cell_type:
                raise InvalidLogError(
                    f'CELL_SELECTED and CELL_EXECUTION_BEGIN cell type mismatch @ line {log_entry_idx_ptr} in file {nb_log_parser.filepath}:\n\n'
                    f'{cell_selected_entry}\n\n'
                    f'{cell_excution_begin_entry}\n\n'
                )

            logger.trace(f'Found CELL_SELECTED entry @ {log_entry_idx_ptr}')
            # logger.trace(f'{nb_log_parser[log_entry_idx_ptr]}')
            # cell_selected_entry contains state of the cell before modification and cell_excution_begin_entry contains state of the cell after modification if any

            # is there modification between cell_selected_entry and cell_excution_begin_entry?
            if cell_selected_entry.content == cell_excution_begin_entry.content:
                logger.trace(f'No modification found @ {log_entry_idx_ptr}.')
                # there is no modification; just execution happened! hence we can skip this entry
                log_entry_idx_ptr = ckpt_ptr + 1
                continue

            # else there is modification, find the corresponding cell in the notebook and apply the modification
            # the modification is replacement with content of cell_excution_begin_entry with cell_selected_entry
            logger.trace(f'Modiciation found @ {log_entry_idx_ptr}.')

            next_step = nb_progress[-1].generate_next_step(
                selected_log_entry=cell_selected_entry,
                start_from_top=True,
                replacement_log_entry=cell_excution_begin_entry
            )

            if next_step is not None:
                nb_progress.append(next_step)
                if verbose:
                    logger.success(f'Log Entry @ {log_entry_idx_ptr} found producing Progress #{len(nb_progress)}')

            else:
                raise NotebookStateLogMismatchError(
                    f'Failed to find corresponding notebook state for log entry @ {log_entry_idx_ptr}'
                )

            log_entry_idx_ptr = ckpt_ptr

        log_entry_idx_ptr += 1

    if verbose:
        logger.success(f'There are {len(nb_progress)} (sub)-notebooks in the progress')

    if len(nb_progress) < 2:
        raise Exception('Failed to find any progress')

    return nb_progress


def get_notebook_progress_simulate(nb_parser_t: NotebookParser, keep_code_header_comments=False, verbose=0):
    nb_progress = []

    for cell_idx in reversed(range(len(nb_parser_t))):
        current_cell = nb_parser_t[cell_idx]
        if current_cell.cell_type != "code":
            continue

        fake_cell_excution_begin_entry = LogEntry(
            entry_type="CELL_EXECUTION_BEGIN",
            content="\\n".join("".join(current_cell.source).split('\n')),
            cell_type=current_cell.cell_type,
            notebook=nb_parser_t.filepath,
            # NOTE: DUMMY arguments as it is simulation
            timestamp=current_cell.cell_id,
            _id=cell_idx*100,
            subject='SIMULATION', user='SIMULATION',
            context='SIMULATION', session_type='SIMULATION',
        )

        if keep_code_header_comments:
            nb_parser_t_minus_1 = nb_parser_t.drop_code(current_cell)
        else:
            nb_parser_t_minus_1 = nb_parser_t.drop_content(current_cell)
        nb_progress.append(
            NBStep(
                nb_parser_state=nb_parser_t, # the new state at time t, before the reverse change
                log_entry=fake_cell_excution_begin_entry,
                cell_id=current_cell.cell_id,
                change_type='INSERT'
            )
        )
        nb_parser_t = nb_parser_t_minus_1

    nb_progress.append(NBStep(nb_parser_t_minus_1))
    nb_progress = list(reversed(nb_progress))
    if verbose:
        logger.success(f'There are {len(nb_progress)} (sub)-notebooks in the progress')

    if len(nb_progress) < 2:
        raise Exception('Failed to find any progress')

    return nb_progress