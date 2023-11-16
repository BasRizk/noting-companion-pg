import textwrap

class NBStep:
    def __init__(self, nb_parser_state, log_entry=None, cell_id=None):
        self.entries = [] if log_entry is None else [log_entry]
        self.cell_id = cell_id
        self.nb_parser_state = nb_parser_state
        self.idx = -1
        self._verify()
        
    def _verify(self):
        _case_1 = (self.cell_id is None and len(self.entries) == 0)
        _case_2 = (len(self.entries) > 0 and self.cell_id is not None)
        return _case_1 or _case_2
    
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
            f"Prev entries:\n{prev_entries_pp}\n" +\
            f"Log entry @ cell_id {self.cell_id}:\n{entry_content_pp}\n" +\
            f"Notebook State:\n{self.nb_parser_state}\n" +\
            f"{'='*80}"
            
    def __repr__(self):
        return self.__str__()
    
    def generate_next_step(self, log_entry, start_from_top=False):
        found_cell = self.nb_parser_state.find_cell_by_content(log_entry.content, start_from_top=start_from_top)
        if found_cell:
            next_step = NBStep(self.nb_parser_state.drop_code(found_cell), log_entry, found_cell.cell_id)
            return next_step
        return None
    
        

def get_notebook_progress(nb_parser, nb_log_parser, verbose=0):
    nb_progress = [NBStep(nb_parser)]
    recent_non_matching_entries = []
    for i, log_entry in enumerate(reversed(nb_log_parser)):
        if log_entry.entry_type == "CELL_EXECUTION_END" and log_entry.cell_type == "code":
            next_step = nb_progress[-1].generate_next_step(log_entry)
            if next_step is not None:
                next_step.add_prev_entries(recent_non_matching_entries)
                recent_non_matching_entries = []
                nb_progress.append(next_step)
                if verbose:
                    print(f'Cell {i} found\nProgress at {i}')
                    # print(nb_progress[-1])
            else:
                if verbose:
                    print('><'*40)
                    entry_content_pp = textwrap.indent('\n'.join(log_entry.content.split('\\n')), '    ')
                    print(f'Cell {i} not found:\n{entry_content_pp}')
                    print('><'*40)           
                recent_non_matching_entries.append(log_entry)

    if len(recent_non_matching_entries):
        raise Exception(f'Failed to place {len(recent_non_matching_entries)} non-matching entries')

    nb_progress = list(reversed(nb_progress))
    if verbose:
        print(f'There are {len(nb_progress)} notebooks in the progress')

    if len(nb_progress) < 2:
        raise Exception('Failed to find any progress')
    return nb_progress
