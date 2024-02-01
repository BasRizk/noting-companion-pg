import textwrap
from _nb_parser import NotebookParser
from _log_parser import LogParser, LogEntry
from loguru import logger

class NBStep:
    def __init__(self, nb_parser_state: NotebookParser, log_entry: LogEntry=None, cell_id: int=None):
        if not isinstance(nb_parser_state, NotebookParser):
            raise Exception(f'Invalid nb_parser_state type: {type(nb_parser_state)}')

        if not (log_entry is None or isinstance(log_entry, LogEntry)):
            raise Exception(f'Invalid log_entry type: {type(log_entry)}')

        self.entries = [] if log_entry is None else [log_entry]
        self.cell_id = cell_id
        self.nb_parser_state = nb_parser_state
        self.idx = -1
        self._verify()

    def _verify(self):
        _case_1 = (self.cell_id is None and len(self.entries) == 0)
        _case_2 = (len(self.entries) > 0 and self.cell_id is not None)
        return _case_1 or _case_2

    def get_change_type(self, change_i):
        if change_i == 0:
            return 'INSERT'
        else:
            return 'UPDATE'

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

    def add_prev_entries(self, prev_log_entries):
        if not isinstance(prev_log_entries, list):
            prev_log_entries = [prev_log_entries]
        self.entries = prev_log_entries + self.entries

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

    def generate_next_step(self, log_entry, start_from_top=False, replacement_log_content=None):
        found_cell = self.nb_parser_state.find_cell_by_content(log_entry.content, start_from_top=start_from_top)
        if found_cell:
            if replacement_log_content is not None:
                new_state = self.nb_parser_state.replace_cell_content(found_cell, replacement_log_content)
            else:
                new_state = self.nb_parser_state.drop_code(found_cell)

            if new_state is None:
                raise Exception(f'Failed to apply log entry to notebook state:\n{log_entry}\n{self.nb_parser_state}')

            next_step = NBStep(new_state, log_entry, found_cell.cell_id)
            return next_step
        return None

from _nb_parser import NotebookParser
from _log_parser import LogParser

class InvalidLog(Exception):
    pass

class NotebookStateLogMismatch(Exception):
    pass

def get_notebook_progress(nb_parser: NotebookParser, nb_log_parser: LogParser, verbose=0):
    nb_progress = [NBStep(nb_parser)]
    recent_non_matching_entries = []
    # reversed_nb_log_parser = reversed(nb_log_parser)
    log_entry_idx_ptr = 0
    while log_entry_idx_ptr < len(nb_log_parser):
        if nb_log_parser[log_entry_idx_ptr].entry_type == "CELL_EXECUTION_END":
            ckpt_ptr = log_entry_idx_ptr # checkpoint

            if nb_log_parser[log_entry_idx_ptr].cell_type != "code":
                raise InvalidLog(f'Non-code CELL_EXECUTION_END cell encountered:\n{nb_log_parser[log_entry_idx_ptr]}')

            logger.debug(f'Found CELL_EXECUTION_END entry @ {log_entry_idx_ptr}')
            # logger.trace(f'{nb_log_parser[log_entry_idx_ptr]}')

            cell_excution_end_entry = nb_log_parser[log_entry_idx_ptr]

            # find the corresponding CELL_EXECUTION_BEGIN entry
            while log_entry_idx_ptr >= 0 and nb_log_parser[log_entry_idx_ptr].entry_type != "CELL_EXECUTION_BEGIN":
                log_entry_idx_ptr -= 1
            if log_entry_idx_ptr < 0:
                raise InvalidLog('Failed to find CELL_EXECUTION_END `CELL_EXECUTION_BEGIN` entry')
            cell_excution_begin_entry = nb_log_parser[log_entry_idx_ptr]

            if cell_excution_begin_entry.cell_type != "code":
                raise InvalidLog(f'Non-code CELL_EXECUTION_BEGIN cell encountered:\n{cell_excution_begin_entry}')

            if cell_excution_begin_entry.content != cell_excution_end_entry.content:
                raise InvalidLog(f'CELL_EXECUTION_BEGIN and CELL_EXECUTION_END content mismatch:\n{cell_excution_begin_entry}\n{cell_excution_end_entry}')

            logger.debug(f'Found CELL_EXECUTION_BEGIN entry @ {log_entry_idx_ptr}')
            # logger.trace(f'{nb_log_parser[log_entry_idx_ptr]}')

            # find the previous CELL_SELECTED entry
            while log_entry_idx_ptr >= 0 and nb_log_parser[log_entry_idx_ptr].entry_type != "CELL_SELECTED":
                log_entry_idx_ptr -= 1
            if log_entry_idx_ptr < 0:
                raise InvalidLog('Failed to find corresponding CELL_SELECTED entry')
            cell_selected_entry = nb_log_parser[log_entry_idx_ptr]

            logger.debug(f'Found CELL_SELECTED entry @ {log_entry_idx_ptr}')
            # logger.trace(f'{nb_log_parser[log_entry_idx_ptr]}')
            # cell_selected_entry contains state of the cell before modification and cell_excution_begin_entry contains state of the cell after modification if any

            # is there modification between cell_selected_entry and cell_excution_begin_entry?
            if cell_selected_entry.content == cell_excution_begin_entry.content:
                logger.debug(f'No modification found @ {log_entry_idx_ptr}.')
                # there is no modification; just execution happened! hence we can skip this entry
                log_entry_idx_ptr = ckpt_ptr + 1
                continue

            logger.debug(f'Modiciation found @ {log_entry_idx_ptr}.')

            # TODO else there is modification, find the corresponding cell in the notebook and apply the modification
            # TODO the modification is replacement with content of cell_excution_begin_entry with cell_selected_entry!!

            next_step = nb_progress[-1].generate_next_step(
                cell_selected_entry,
                start_from_top=True,
                replacement_log_content=cell_excution_begin_entry.content
            )

            if next_step is not None:
                next_step.add_prev_entries(recent_non_matching_entries)
                recent_non_matching_entries = []
                nb_progress.append(next_step)
                if verbose:
                    logger.success(f'Log Entry @ {log_entry_idx_ptr} found producing Progress #{len(nb_progress)}')
            else:
                if verbose:
                    print('><'*40)
                    entry_content_pp = textwrap.indent('\n'.join(cell_excution_end_entry.content.split('\\n')), '    ')
                    print(f'Cell {log_entry_idx_ptr} not found:\n{entry_content_pp}')
                    print('><'*40)
                recent_non_matching_entries.append(cell_excution_end_entry)

            log_entry_idx_ptr = ckpt_ptr

        log_entry_idx_ptr += 1


    if len(recent_non_matching_entries):
        # breakpoint()
        raise NotebookStateLogMismatch(f'Failed to place {len(recent_non_matching_entries)} non-matching entries')

    # nb_progress = list(reversed(nb_progress))
    if verbose:
        print(f'There are {len(nb_progress)} notebooks in the progress')

    if len(nb_progress) < 2:
        raise Exception('Failed to find any progress')
    return nb_progress


# from _log_parser import LogParser
# from _nb_parser import NotebookParser

# def get_all_notebooks_progress(nb_log_parser: LogParser, all_notebooks_filepaths, verbose=0):
#     open_notebooks_progress = {}
#     # skipped_notebooks = []
#     # nb_progress = [NBStep(nb_parser)]
#     recent_non_matching_entries = []
#     for i, log_entry in enumerate(reversed(nb_log_parser)):
#         nb_log_parser
#         if log_entry.entry_type == "CELL_EXECUTION_END" and log_entry.cell_type == "code":
#             next_step = nb_progress[-1].generate_next_step(log_entry)
#             if next_step is not None:
#                 next_step.add_prev_entries(recent_non_matching_entries)
#                 recent_non_matching_entries = []
#                 nb_progress.append(next_step)
#                 if verbose:
#                     print(f'Cell {i} found\nProgress at {i}')
#                     # print(nb_progress[-1])
#             else:
#                 if verbose:
#                     print('><'*40)
#                     entry_content_pp = textwrap.indent('\n'.join(log_entry.content.split('\\n')), '    ')
#                     print(f'Cell {i} not found:\n{entry_content_pp}')
#                     print('><'*40)
#                 recent_non_matching_entries.append(log_entry)

#     if len(recent_non_matching_entries):
#         breakpoint()
#         raise Exception(f'Failed to place {len(recent_non_matching_entries)} non-matching entries')

#     nb_progress = list(reversed(nb_progress))
#     if verbose:
#         print(f'There are {len(nb_progress)} notebooks in the progress')

#     if len(nb_progress) < 2:
#         raise Exception('Failed to find any progress')
#     return nb_progress