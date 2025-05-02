from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import requests
import os
import re
import time
import getpass
import base64
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from cryptography.fernet import Fernet

WIKI_API_URL = "https://en.wikipedia.org/w/api.php"

# this is where the API gets called

def fetch_article(title):
    """Try to fetch a Wikipedia article's content by its title."""
    params = {
        "action": "query",
        "format": "json",
        "prop": "extracts",
        "titles": title,
        "explaintext": True,
    }

    try:
        response = requests.get(WIKI_API_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as e:
        print(f"[ERROR] Error fetching article '{title}': {e}")
        return None, None

    # Grab the page content from the response
    try:
        page = next(iter(data["query"]["pages"].values()))
        return page["title"], page.get("extract", "")
    except (KeyError, StopIteration):
        print(f"[ERROR] Unexpected response structure for '{title}'.")
        return None, None

def fetch_links(title):
    """Fetch internal links from the Wikipedia article.
    
    Args:
        title (str): The title of the Wikipedia article.
        
    Returns:
        list: List of linked article titles.
    """
    links = []
    plcontinue = None

    while True:
        params = {
            "action": "query",
            "format": "json",
            "prop": "links",
            "titles": title,
            "pllimit": "max",
        }
        if plcontinue:
            params["plcontinue"] = plcontinue

        try:
            response = requests.get(WIKI_API_URL, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as e:
            print(f"[ERROR] Error fetching links for '{title}': {e}")
            break

        if "query" not in data or "pages" not in data["query"]:
            print(f"[ERROR] Unexpected API response structure when fetching links for '{title}'.")
            break

        page = next(iter(data["query"]["pages"].values()))

        if "links" in page:
            # Exclude Help pages
            links.extend(link["title"] for link in page["links"] if not link["title"].startswith("Help:"))

        if "continue" in data and "plcontinue" in data["continue"]:
            plcontinue = data["continue"]["plcontinue"]
        else:
            break

    return links

# This is the file saving section

def sanitize_filename(title):
    """Sanitize the filename by replacing non-alphanumeric characters with underscores."""
    safe_title = re.sub(r'[^A-Za-z0-9]+', '_', title).strip('_')
    return safe_title or "article"

def get_user_key():
    """Derive a cryptographic key from a user-supplied password using PBKDF2HMAC."""
    password = getpass.getpass("Enter password for key derivation: ").encode()
    salt = b'some_fixed_salt'  # In real use, use a secure random salt and store it
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
        backend=default_backend()
    )
    key = base64.urlsafe_b64encode(kdf.derive(password))
    return key

def save_article(title, content, folder="articles", fmt="txt", fernet_key=None):
    """Save the article to a file — optionally as .txt, .html, or .md — and encrypt if needed.

    Args:
        title (str): Article title.
        content (str): Article content.
        folder (str): Folder to save the file.
        fmt (str): File format ('txt', 'html', 'md').
        fernet_key (bytes or None): Encryption key for encrypting content.
    """
    safe_title = sanitize_filename(title)
    os.makedirs(folder, exist_ok=True)
    filename = os.path.join(folder, f"{safe_title}.{fmt}")

    if fmt == "html":
        content = f"<html><body><h1>{title}</h1><p>{content.replace(chr(10), '<br>')}</p></body></html>"
    elif fmt == "md":
        content = f"# {title}\n\n{content}"

    if fernet_key:
        content = Fernet(fernet_key).encrypt(content.encode()).decode()

    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[SUCCESS] Saved article as '{filename}'")
    except OSError as e:
        print(f"[ERROR] Error saving article '{title}': {e}")

# main logic area

def main():
    """Main program logic for crawling Wikipedia articles."""
    while True:
        subject = input("Enter a Wikipedia topic: ").strip()
        if subject:
            break
        print("[ERROR] Topic cannot be empty. Please enter a valid Wikipedia topic.")

    title, content = fetch_article(subject)

    if not content:
        print("[ERROR] Article not found.")
        return

    fmt = input("Choose a file format (txt/html/md) [txt]: ").strip().lower()
    if fmt not in ("txt", "html", "md"):
        fmt = "txt"

    folder = input("Enter folder name to save articles [articles]: ").strip()
    if not folder:
        folder = "articles"

    encrypt_choice = input("Would you like to encrypt the saved files? [y/N]: ").strip().lower()
    encrypt_files = encrypt_choice == 'y'

    fernet_key = get_user_key() if encrypt_files else None

    save_article(title, content, folder, fmt, fernet_key=fernet_key)

    links = fetch_links(title)
    print(f"[INFO] Found {len(links)} internal article links.")
    for link in links[:10]:  # Show first 10 as preview
        print(f"   - {link}")

    max_links_input = input("How many linked articles would you like to crawl? [default 50, max 100]: ").strip()
    try:
        max_links = min(100, max(1, int(max_links_input)))
    except ValueError:
        max_links = 50
    links = links[:max_links]

    choice = input("Would you like to crawl and save linked articles? [y/N]: ").strip().lower()
    if choice == "y":
        cpu_count = os.cpu_count() or 2
        if cpu_count < 4:
            max_threads = 2
        else:
            max_threads = min(10, cpu_count * 2)

        print(f"[INFO] Using up to {max_threads} threads for crawling.")

        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            futures = {executor.submit(fetch_article, link): link for link in links}
            for i, future in enumerate(
                tqdm(as_completed(futures), total=len(futures), desc="Crawling"), 1
            ):
                link = futures[future]
                try:
                    linked_title, linked_content = future.result()
                    if linked_content:
                        save_article(linked_title, linked_content, folder, fmt, fernet_key=fernet_key)
                except Exception as e:
                    print(f"[{i}/{len(links)}] [ERROR] Error fetching {link}: {e}")

if __name__ == "__main__":
    main()