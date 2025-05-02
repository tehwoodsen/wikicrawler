


# WikiCrawler

WikiCrawler is a simple command-line tool that lets you download and save Wikipedia articles. You can enter a topic, save the article locally in your preferred format (text, HTML, or Markdown), and even choose to crawl and save linked articles within the same page.

## Features

- Search and download Wikipedia articles by title
- Save articles as `.txt`, `.html`, or `.md`
- Optional encryption of saved content using a password
- Option to crawl and save internal links found in the article
- Multithreaded crawling for faster performance

## Getting Started

### Requirements

- Python 3.7+
- pip

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run the Script

```bash
python main.py
```

You'll be prompted to enter a Wikipedia topic, choose a format, and decide if you want to crawl related links.

## Encryption

If you choose to encrypt your saved files, you'll be asked for a password. This password is used to derive a secure key, but the key is never stored on disk. Don't forget your password — there's no recovery option.

## Notes

- Crawling many pages may take some time depending on your system and network speed.
- This project is intended for educational and personal use.

## To Do

- Add support for resuming interrupted crawls
- Improve formatting of saved HTML/Markdown files
- GUI version?

## License

MIT License