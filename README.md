# noting-companion-pg

### Instructions to run:
0. Install the required packages:
    ```bash
    pip install -r requirements.txt
    ```

1. Ensure you have `data` folder including the following:
    - `data/tac_notebooks/tac_notebooks` including subjects directories named in this pattern `r'.+-Subject-\d+'`, and containing notebooks starter codes used in the respective session.
    - `data/tac_raw_logs` including the log directories named in this pattern `r'subject-\d+'`, and containing the raw logs of the respective session. Each containing log file named `knic-tac-evaluation.log`.

2. Run the following command to generate the companion notebook:
    ```bash
    python analyze_nb_logs.py
    ```