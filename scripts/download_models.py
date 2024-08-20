
import requests
from tqdm import tqdm
from pathlib import Path

def get_filename_from_link(file_link):
    return f"models\{file_link.split(r'/')[-1]}"

def download_file(url):
    filename = get_filename_from_link(url)

    if Path(filename).is_file():
        print(f"Skipping {filename} as it is already downloaded ")
    else:        
        response = requests.get(url, stream=True)

        # Sizes in bytes.
        total_size = int(response.headers.get("content-length", 0))
        block_size = 1024

        with tqdm(total=total_size, unit="B", unit_scale=True) as progress_bar:
            with open(filename, "wb") as file:
                for data in response.iter_content(block_size):
                    progress_bar.update(len(data))
                    file.write(data)

        if total_size != 0 and progress_bar.n != total_size:
            raise RuntimeError("Could not download file")
model_links = open("scripts\model_links.txt").read().splitlines()

for link in model_links:
    download_file(link)
