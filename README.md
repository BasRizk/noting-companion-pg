# noting-companion-pg

## Install the required packages:
```bash
pip install -r requirements.txt
```


## Two analysis options:
### **(1)** Start analysis of alignment between the starter codes and the logs:
        ```bash
        python analyze_nb_logs.py
        ```

#### Ensure you have `data` folder including the following:
- `data/tac_notebooks/tac_notebooks` including subjects directories named in this pattern `r'.+-Subject-\d+'`, and containing notebooks starter codes used in the respective session.
- `data/tac_raw_logs` including the log directories named in this pattern `r'subject-\d+'`, and containing the raw logs of the respective session. Each containing log file named `knic-tac-evaluation.log`.



#### Parameters:
- `--notebooks_dir` path to the notebooks directory (default: `data/tac_notebooks`)
- `--logs_dir` path to the logs directory (default: `data/tac_raw_logs`)
- `--append_prev_msgs` whether to append the previous messages to the current message (default: `False`)


### **(2)** Start analysis with simulation notebooks progress using no logs (dummy each code cell correspond to one step at time):
    ```bash
    python analyze_simulated_nb_progress.py
    ```


#### Parameters:
- `--notebooks_dir` path to the notebooks directory (default: `data/tac_notebooks`)
- `--append_prev_msgs` whether to append the previous messages to the current message (default: `False`)
- `--keep_code_header_comments` whether to keep the comments in the code cells (the ones on top like `# INSTRUCTION: ...`) (default: `False`)