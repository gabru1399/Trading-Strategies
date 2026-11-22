import os, shutil

dirs_to_clean = [
    r'c:\Users\SIGMA\Documents\Trading-Strategies',
    r'C:\Users\SIGMA\.gemini\config',
    r'C:\Users\SIGMA\.gemini\antigravity'
]

removed_count = 0
total_size = 0

for base in dirs_to_clean:
    if os.path.exists(base):
        for root, dirs, files in os.walk(base):
            if '__pycache__' in dirs:
                pyc_path = os.path.join(root, '__pycache__')
                try:
                    sz = sum(os.path.getsize(os.path.join(r, f)) for r, d, f_list in os.walk(pyc_path) for f in f_list)
                    shutil.rmtree(pyc_path)
                    removed_count += 1
                    total_size += sz
                except Exception as e:
                    print(f'Error deleting {pyc_path}: {e}')

print(f'Cleaned {removed_count} __pycache__ directories, reclaimed {total_size / (1024*1024):.2f} MB!')
