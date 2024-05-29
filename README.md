# noting-companion-pg

## Install the required packages in `python 3.10` environment:
```bash
pip install -r requirements.txt
```

## Use Cases:
### **(1)**  Generate QA pairs with real logs example:

#### Ensure you have `data` folder including the following:
- `data/tac_notebooks/tac_notebooks` including subjects directories named in this pattern `r'.+-Subject-\d+'`, and containing notebooks starter codes used in the respective session.
- `data/tac_raw_logs` including the log directories named in this pattern `r'subject-\d+'`, and containing the raw logs of the respective session. Each containing log file named `knic-tac-evaluation.log`.

```bash
python generate_qa_pairs.py --notebooks_dir data/tac_notebooks --logs_dir data/tac_raw_logs --min_num_steps 4 --output_dir generated_qa_pairs --methods "offline" "mix"
```

### **(2)** Generate QA pairs with simulate logs (without logs) example (dummy each code cell correspond to one step at time):
    ```bash
    python generate_qa_pairs.py --notebooks_dir data/online_notebooks --simulate_log --methods "offline" "mix" --output_dir generated_qa_pairs
    ```

#### Parameters of `generate_qa_pairs.py`:
- `--notebooks_dir` path to the notebooks directory (default: `data/tac_notebooks`)
- `--logs_dir` path to the logs directory (default: `data/tac_raw_logs`)
- `--simulate_log` whether to simulate the logs (default: `False`)
- `--min_num_steps` minimum number of steps to consider a session (default: `4`)
- `--output_dir` path to the output directory (default: `generated_qa_pairs`)
- `--methods` methods to use for generating QA pairs (default: `"offline" "mix"`)
    - `--online` generate QA pairs using currently deployed method on `https://ckg12.isi.edu/knic-services/generate_questions`.
    - `--offline` generate QA pairs using offline method.
    - `--mix` generate QA pairs using both online then reanswer the generated questions using offline method answers generation procedure.
