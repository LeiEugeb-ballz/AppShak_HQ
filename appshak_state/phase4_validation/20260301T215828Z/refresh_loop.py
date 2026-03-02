import subprocess
import time
for _ in range(30):
    subprocess.run(['python','-m','appshak_integrity.run_report','--window','7d'], check=False)
    subprocess.run(['python','-m','appshak_inspection.run_index'], check=False)
    time.sleep(20)