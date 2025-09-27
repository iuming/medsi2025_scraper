#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MEDSI2025 Conference Web Scraper

Author: Ming Liu
Date: September 27, 2025
Description: A comprehensive web scraper for MEDSI2025 conference papers and abstracts.
             Extracts paper information organized by sessions, downloads PDFs, and exports
             data in multiple formats (JSON, CSV, TXT).

Website: https://meow.elettra.eu/88/
Features:
- Session-based paper extraction
- PDF download with validation
- Multi-format data export
- Robust error handling and retry mechanisms
- Comprehensive logging
"""

import requests
from bs4 import BeautifulSoup
import os
import json
import time
import re
from urllib.parse import urljoin, urlparse
from typing import Dict, List, Any, Optional
import logging
from pathlib import Path

class MEDSI2025Scraper:
    """
    Web scraper for MEDSI2025 conference proceedings.
    
    This scraper extracts paper information from the MEDSI2025 conference website,
    organizing data by sessions and downloading available PDF files.
    """
    
    def __init__(self, base_url: str = "https://meow.elettra.eu/88/", output_dir: str = "MEDSI2025_Data"):
        """
        Initialize the MEDSI2025 scraper.
        
        Args:
            base_url: Base URL of the MEDSI2025 conference website
            output_dir: Directory to store scraped data and PDFs
        """
        self.base_url = base_url
        self.output_dir = Path(output_dir)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('medsi2025_scraper.log', encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # MEDSI2025 session configuration
        self.sessions_config = [
            {'id': '936-tuka', 'name': 'TUKA - Welcome & MEDSI 25th Anniversary Keynote', 'prefix': 'TUKA'},
            {'id': '1037-tukb', 'name': 'TUKB - Keynote Session 2', 'prefix': 'TUKB'},
            {'id': '1038-tuoa', 'name': 'TUOA - Beamlines Session 1', 'prefix': 'TUOA'},
            {'id': '1039-tuob', 'name': 'TUOB - Beamlines Session 2', 'prefix': 'TUOB'},
            {'id': '928-tup', 'name': 'TUP - Poster Session 1', 'prefix': 'TUP'},
            {'id': '1040-weoa', 'name': 'WEOA - Beamlines Session 3', 'prefix': 'WEOA'},
            {'id': '1041-weob', 'name': 'WEOB - Accelerators Session 1', 'prefix': 'WEOB'},
            {'id': '1042-weoc', 'name': 'WEOC - Accelerators Session 2', 'prefix': 'WEOC'},
            {'id': '929-wep', 'name': 'WEP - Poster Session 2', 'prefix': 'WEP'},
            {'id': '1043-thoa', 'name': 'THOA - Simulation session 1', 'prefix': 'THOA'},
            {'id': '1044-thob', 'name': 'THOB - Simulation Session 2', 'prefix': 'THOB'},
            {'id': '1045-thoc', 'name': 'THOC - New Facility Design and Upgrade Session', 'prefix': 'THOC'},
            {'id': '1046-thod', 'name': 'THOD - Precision Mechanics Session', 'prefix': 'THOD'},
            {'id': '930-thp', 'name': 'THP - Poster Session 3', 'prefix': 'THP'},
            {'id': '1002-froa', 'name': 'FROA - Core Technology Developments Session 1', 'prefix': 'FROA'},
            {'id': '1047-frob', 'name': 'FROB - Core Technology Developments Session 2', 'prefix': 'FROB'}
        ]
        
        # Initialize directories and statistics
        self.create_directories()
        self.stats = {'total_papers': 0, 'downloaded_pdfs': 0, 'errors': 0, 'sessions_processed': 0}
    
    def create_directories(self):
        """Create necessary directory structure for output files."""
        self.output_dir.mkdir(exist_ok=True)
        (self.output_dir / "PDFs").mkdir(exist_ok=True)
        (self.output_dir / "Sessions").mkdir(exist_ok=True)
        (self.output_dir / "Debug").mkdir(exist_ok=True)
        self.logger.info(f"Created output directory: {self.output_dir}")
    
    def safe_filename(self, filename: str, max_length: int = 180) -> str:
        """
        Convert filename to safe filesystem name.
        
        Args:
            filename: Original filename
            max_length: Maximum allowed filename length
            
        Returns:
            Safe filename string
        """
        if not filename:
            return "unknown"
        
        # Remove invalid characters
        filename = re.sub(r'[<>:"/\\|?*\r\n]', '_', filename)
        filename = re.sub(r'\s+', ' ', filename)
        filename = filename.strip(' ._')
        
        # Truncate if too long
        if len(filename) > max_length:
            filename = filename[:max_length].rsplit(' ', 1)[0]
        
        return filename or "unknown"
    
    def get_page_content(self, url: str, retries: int = 3) -> Optional[BeautifulSoup]:
        """
        Get webpage content with retry mechanism.
        
        Args:
            url: URL to fetch
            retries: Number of retry attempts
            
        Returns:
            BeautifulSoup object or None if failed
        """
        for attempt in range(retries):
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                return BeautifulSoup(response.text, 'html.parser')
            except requests.RequestException as e:
                self.logger.warning(f"Failed to fetch page (attempt {attempt + 1}/{retries}) {url}: {e}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    self.logger.error(f"Final failure fetching page {url}: {e}")
                    self.stats['errors'] += 1
        return None
    
    def extract_papers_from_session(self, soup: BeautifulSoup, session_prefix: str) -> List[Dict[str, Any]]:
        """
        Extract paper information from a session page.
        
        Args:
            soup: BeautifulSoup object of the session page
            session_prefix: Session prefix (e.g., 'TUOA', 'TUP')
            
        Returns:
            List of paper dictionaries
        """
        papers = []
        page_text = soup.get_text()
        
        # Save debug information
        debug_file = self.output_dir / "Debug" / f"{session_prefix}_page_text.txt"
        with open(debug_file, 'w', encoding='utf-8') as f:
            f.write(page_text)
        
        # Enhanced paper matching pattern supporting multiple end markers
        pattern = rf'({session_prefix}\d{{2,3}})([A-Za-z][^0-9]*?)(\d+)(.*?)(?=(?:Paper:|Cite:|{session_prefix}\d{{2,3}}(?![0-9])|$))'
        
        matches = re.findall(pattern, page_text, re.DOTALL)
        
        self.logger.info(f"Session {session_prefix} found {len(matches)} paper matches")
        
        # Process matches and filter duplicates
        seen_papers = set()
        for paper_id, title_raw, page_num, content_raw in matches:
            if paper_id in seen_papers:
                continue  # Skip duplicate paper IDs
            
            # Filter out non-paper title content
            title = title_raw.strip()
            if any(keyword in title for keyword in ['DOI:', 'About:', 'Cite:', 'reference for this paper']):
                continue
            
            # Filter out page numbers misidentified as paper IDs
            if len(paper_id) < 5:  # Paper IDs should be at least 5 characters
                continue
            
            seen_papers.add(paper_id)
            
            paper_info = self.extract_paper_details(paper_id, title, page_num, content_raw.strip())
            
            if paper_info:
                papers.append(paper_info)
                self.logger.info(f"  ✓ {paper_id}: {paper_info['title'][:50]}...")
        
        return papers
    
    def extract_paper_details(self, paper_id: str, title_raw: str, page_num: str, content: str) -> Dict[str, Any]:
        """
        Extract detailed information for a single paper.
        
        Args:
            paper_id: Paper ID (e.g., 'TUOA01')
            title_raw: Raw paper title
            page_num: Page number
            content: Raw content text
            
        Returns:
            Dictionary containing paper information
        """
        paper_info = {
            'paper_id': paper_id,
            'title': title_raw,
            'authors': [],
            'institutions': [],
            'abstract': '',
            'pdf_url': urljoin(self.base_url, f"pdf/{paper_id}.pdf"),
            'doi': f"https://doi.org/10.18429/JACoW-MEDSI2025-{paper_id}",
            'received_date': '',
            'accepted_date': '',
            'page_number': page_num,
            'pdf_available': False
        }
        
        # Analyze content to extract abstract and author information
        lines = content.split('\n')
        abstract_lines = []
        author_section = ""
        
        # Find author section (usually at the end, short lines with uppercase letters)
        author_started = False
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
                
            # Check if this is the start of author information
            if (not author_started and 
                (re.match(r'^[A-Z]\.\s+[A-Z][a-z]+', line) or 
                 (len(line.split()) <= 8 and any(c.isupper() for c in line[:5])))):
                author_started = True
                author_section = line
                continue
                
            # Continue collecting author information
            if author_started:
                if any(keyword in line for keyword in ['Paper:', 'DOI:', 'About:', 'Received:', 'Cite:']):
                    # Stop when encountering metadata
                    break
                author_section += " " + line
            else:
                # Still in abstract section
                if len(line) > 20:  # Lines long enough to be abstract content
                    abstract_lines.append(line)
        
        if abstract_lines:
            paper_info['abstract'] = ' '.join(abstract_lines)
        
        # Parse author and institution information
        if author_section:
            self.parse_authors_and_institutions(author_section, paper_info)
        
        # Extract date information from content
        received_match = re.search(r'Received:\s*(\d{1,2}\s+\w+\s+\d{4})', content)
        if received_match:
            paper_info['received_date'] = received_match.group(1)
            
        accepted_match = re.search(r'Accepted:\s*(\d{1,2}\s+\w+\s+\d{4})', content)
        if accepted_match:
            paper_info['accepted_date'] = accepted_match.group(1)
        
        # Check PDF availability
        paper_info['pdf_available'] = self.check_pdf_exists(paper_info['pdf_url'])
        
        return paper_info
    
    def parse_authors_and_institutions(self, author_text: str, paper_info: Dict[str, Any]):
        """
        Parse author and institution information from text.
        
        Args:
            author_text: Raw author text
            paper_info: Paper information dictionary to update
        """
        # Split by double or more spaces to separate authors from institutions
        parts = re.split(r'\s{2,}', author_text)
        
        if len(parts) >= 2:
            author_part = parts[0].strip()
            institution_part = ' '.join(parts[1:]).strip()
            
            # Parse authors (usually comma-separated)
            if author_part:
                authors = [a.strip() for a in author_part.split(',') if a.strip()]
                paper_info['authors'] = authors
            
            # Parse institutions
            if institution_part:
                # Institutions may be separated by semicolons or special characters
                institutions = [inst.strip() for inst in re.split(r'[;,](?=[A-Z])', institution_part) if inst.strip()]
                paper_info['institutions'] = institutions
        else:
            # If no clear separation, try simple parsing
            text = author_text.strip()
            if text:
                # Look for obvious institution keywords
                institution_keywords = ['University', 'Laboratory', 'Institute', 'Center', 'Corporation', 
                                      'School', 'Facility', 'Source', 'Accelerator', 'National', 'Synchrotron']
                
                if any(keyword in text for keyword in institution_keywords):
                    paper_info['institutions'].append(text)
                else:
                    # Likely author names
                    authors = [a.strip() for a in text.split(',') if a.strip()]
                    paper_info['authors'] = authors
    
    def check_pdf_exists(self, pdf_url: str) -> bool:
        """
        Check if PDF file exists and is accessible.
        
        Args:
            pdf_url: URL of the PDF file
            
        Returns:
            True if PDF exists and is accessible
        """
        try:
            response = self.session.head(pdf_url, timeout=10)
            return response.status_code == 200 and 'pdf' in response.headers.get('content-type', '').lower()
        except:
            return False
    
    def scrape_session(self, session: Dict[str, str]) -> List[Dict[str, Any]]:
        """
        Scrape all papers from a single session.
        
        Args:
            session: Session configuration dictionary
            
        Returns:
            List of paper dictionaries
        """
        self.logger.info(f"Scraping session: {session['name']}")
        
        soup = self.get_page_content(session['url'])
        if not soup:
            return []
        
        papers = self.extract_papers_from_session(soup, session['prefix'])
        
        self.stats['total_papers'] += len(papers)
        self.stats['sessions_processed'] += 1
        
        self.logger.info(f"Session {session['prefix']} results: {len(papers)} papers")
        
        # Display found papers
        for i, paper in enumerate(papers):
            pdf_status = "✓" if paper['pdf_available'] else "✗"
            self.logger.info(f"  {i+1}. {paper['paper_id']}: {paper['title'][:50]}... [PDF:{pdf_status}]")
        
        return papers
    
    def download_pdf(self, pdf_url: str, paper_info: Dict[str, Any], session_name: str) -> bool:
        """
        Download PDF file for a paper.
        
        Args:
            pdf_url: URL of the PDF file
            paper_info: Paper information dictionary
            session_name: Name of the session
            
        Returns:
            True if download successful
        """
        if not paper_info.get('pdf_available', False):
            return False
            
        try:
            session_pdf_dir = self.output_dir / "PDFs" / self.safe_filename(session_name)
            session_pdf_dir.mkdir(exist_ok=True)
            
            filename = f"{paper_info['paper_id']} - {paper_info['title']}"
            safe_name = self.safe_filename(filename)
            if not safe_name.endswith('.pdf'):
                safe_name += '.pdf'
            
            filepath = session_pdf_dir / safe_name
            
            if filepath.exists():
                self.logger.info(f"PDF already exists, skipping: {safe_name}")
                return True
            
            response = self.session.get(pdf_url, stream=True, timeout=60)
            response.raise_for_status()
            
            content_length = int(response.headers.get('content-length', 0))
            if content_length > 0 and content_length < 100:  # Skip obviously wrong small files
                self.logger.warning(f"PDF file too small ({content_length} bytes), skipping: {paper_info['paper_id']}")
                return False
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            self.stats['downloaded_pdfs'] += 1
            self.logger.info(f"✅ Downloaded PDF: {safe_name} ({content_length} bytes)")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to download PDF {pdf_url}: {e}")
            self.stats['errors'] += 1
            return False
    
    def save_session_data(self, session: Dict[str, str], papers: List[Dict[str, Any]]):
        """
        Save session data to files in multiple formats.
        
        Args:
            session: Session configuration dictionary
            papers: List of paper dictionaries
        """
        session_dir = self.output_dir / "Sessions" / self.safe_filename(session['name'])
        session_dir.mkdir(parents=True, exist_ok=True)
        
        # JSON format
        json_file = session_dir / "papers_data.json"
        session_data = {
            'session_info': session,
            'papers': papers,
            'paper_count': len(papers),
            'scrape_time': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, ensure_ascii=False, indent=2)
        
        # CSV format
        self.save_session_csv(session_dir, papers, session)
        
        # Text format
        self.save_session_txt(session_dir, session, papers)
        
        self.logger.info(f"Saved session data: {session['name']} ({len(papers)} papers)")
    
    def save_session_csv(self, session_dir: Path, papers: List[Dict[str, Any]], session: Dict[str, str]):
        """Save session data in CSV format."""
        import csv
        
        csv_file = session_dir / "papers_data.csv"
        with open(csv_file, 'w', newline='', encoding='utf-8-sig') as f:
            if not papers:
                return
                
            fieldnames = ['session_name', 'paper_id', 'title', 'authors', 'institutions', 'abstract', 
                         'pdf_url', 'pdf_available', 'doi', 'page_number', 'received_date', 'accepted_date']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for paper in papers:
                row = {
                    'session_name': session['name'],
                    **paper
                }
                row['authors'] = '; '.join(paper['authors'])
                row['institutions'] = '; '.join(paper['institutions'])
                writer.writerow(row)
    
    def save_session_txt(self, session_dir: Path, session: Dict[str, str], papers: List[Dict[str, Any]]):
        """Save session data in text format."""
        txt_file = session_dir / "papers_summary.txt"
        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write(f"Session: {session['name']}\n")
            f.write(f"Session ID: {session['id']}\n")
            f.write(f"URL: {session['url']}\n")
            f.write(f"Scrape time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Paper count: {len(papers)}\n")
            available_pdfs = sum(1 for p in papers if p.get('pdf_available', False))
            f.write(f"Available PDFs: {available_pdfs}/{len(papers)}\n")
            f.write("=" * 80 + "\n\n")
            
            for i, paper in enumerate(papers, 1):
                pdf_status = "✓ Available" if paper.get('pdf_available', False) else "✗ Not available"
                f.write(f"{i}. Paper ID: {paper['paper_id']}\n")
                f.write(f"   Title: {paper['title']}\n")
                if paper['authors']:
                    f.write(f"   Authors: {', '.join(paper['authors'])}\n")
                if paper['institutions']:
                    f.write(f"   Institutions: {'; '.join(paper['institutions'])}\n")
                f.write(f"   Page: {paper.get('page_number', 'N/A')}\n")
                f.write(f"   PDF Status: {pdf_status}\n")
                f.write(f"   PDF URL: {paper['pdf_url']}\n")
                if paper['doi']:
                    f.write(f"   DOI: {paper['doi']}\n")
                if paper['received_date']:
                    f.write(f"   Received: {paper['received_date']}\n")
                if paper['accepted_date']:
                    f.write(f"   Accepted: {paper['accepted_date']}\n")
                if paper['abstract']:
                    abstract_preview = paper['abstract'][:300] + '...' if len(paper['abstract']) > 300 else paper['abstract']
                    f.write(f"   Abstract: {abstract_preview}\n")
                f.write("-" * 60 + "\n")
    
    def create_final_summary(self, all_sessions_data: List[Dict]):
        """
        Create final summary report of all scraped data.
        
        Args:
            all_sessions_data: List of all session data dictionaries
        """
        # Calculate statistics
        total_available_pdfs = sum(
            sum(1 for paper in session_data['papers'] if paper.get('pdf_available', False))
            for session_data in all_sessions_data
        )
        
        # Text summary
        summary_file = self.output_dir / "MEDSI2025_Final_Report.txt"
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write("MEDSI2025 Conference Complete Scraping Report\n")
            f.write("=" * 60 + "\n")
            f.write(f"Scrape completion time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Sessions processed: {self.stats['sessions_processed']}\n")
            f.write(f"Total papers: {self.stats['total_papers']}\n")
            f.write(f"Available PDFs: {total_available_pdfs}\n")
            f.write(f"Successfully downloaded PDFs: {self.stats['downloaded_pdfs']}\n")
            f.write(f"Download success rate: {(self.stats['downloaded_pdfs']/total_available_pdfs*100):.1f}%\n" if total_available_pdfs > 0 else "Download success rate: 0%\n")
            f.write(f"Errors: {self.stats['errors']}\n\n")
            
            f.write("Session detailed statistics:\n")
            f.write("-" * 50 + "\n")
            for session_data in all_sessions_data:
                session = session_data['session_info']
                papers = session_data['papers']
                available_pdfs = sum(1 for p in papers if p.get('pdf_available', False))
                
                f.write(f"Session: {session['name']}\n")
                f.write(f"   Papers: {len(papers)}\n")
                f.write(f"   Available PDFs: {available_pdfs}\n")
                f.write(f"   URL: {session['url']}\n")
                
                if papers:
                    f.write("   Paper list:\n")
                    for paper in papers:
                        pdf_icon = "PDF" if paper.get('pdf_available', False) else "---"
                        f.write(f"     [{pdf_icon}] {paper['paper_id']}: {paper['title'][:60]}...\n")
                f.write("\n")
        
        # JSON index
        master_json = self.output_dir / "MEDSI2025_Complete_Index.json"
        with open(master_json, 'w', encoding='utf-8') as f:
            json.dump({
                'scrape_info': {
                    'scrape_time': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'sessions_processed': self.stats['sessions_processed'],
                    'total_papers': self.stats['total_papers'],
                    'available_pdfs': total_available_pdfs,
                    'downloaded_pdfs': self.stats['downloaded_pdfs'],
                    'download_success_rate': f"{(self.stats['downloaded_pdfs']/total_available_pdfs*100):.1f}%" if total_available_pdfs > 0 else "0%",
                    'errors': self.stats['errors']
                },
                'sessions': all_sessions_data
            }, f, ensure_ascii=False, indent=2)
        
        # Create master CSV
        self.create_master_csv(all_sessions_data)
    
    def create_master_csv(self, all_sessions_data: List[Dict]):
        """Create master CSV file containing all papers."""
        import csv
        
        csv_file = self.output_dir / "MEDSI2025_All_Papers.csv"
        with open(csv_file, 'w', newline='', encoding='utf-8-sig') as f:
            fieldnames = ['session_name', 'session_id', 'paper_id', 'title', 'authors', 'institutions', 
                         'abstract', 'pdf_url', 'pdf_available', 'doi', 'page_number', 'received_date', 'accepted_date']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for session_data in all_sessions_data:
                session_info = session_data['session_info']
                for paper in session_data['papers']:
                    row = {
                        'session_name': session_info['name'],
                        'session_id': session_info['id'],
                        **paper
                    }
                    row['authors'] = '; '.join(paper['authors'])
                    row['institutions'] = '; '.join(paper['institutions'])
                    writer.writerow(row)
    
    def run(self, test_mode: bool = False):
        """
        Run the main scraping process.
        
        Args:
            test_mode: If True, only process first 3 sessions for testing
            
        Returns:
            List of all session data
        """
        self.logger.info("Starting MEDSI2025 conference data scraping")
        start_time = time.time()
        
        try:
            sessions = []
            for session_info in self.sessions_config:
                sessions.append({
                    'id': session_info['id'],
                    'name': session_info['name'],
                    'url': urljoin(self.base_url, f"session/{session_info['id']}/index.html"),
                    'prefix': session_info['prefix']
                })
            
            self.logger.info(f"Prepared to process {len(sessions)} sessions")
            
            if test_mode:
                sessions = sessions[2:5]  # Test with TUOA, TUOB, TUP
                self.logger.info(f"Test mode: processing sessions TUOA, TUOB, TUP")
            
            all_sessions_data = []
            
            # Process each session
            for i, session in enumerate(sessions, 1):
                self.logger.info(f"\nProcessing session {i}/{len(sessions)}: {session['name']}")
                
                try:
                    papers = self.scrape_session(session)
                    
                    if papers:
                        self.save_session_data(session, papers)
                        
                        # Download PDF files
                        available_pdfs = [p for p in papers if p.get('pdf_available', False)]
                        pdf_downloaded = 0
                        
                        for paper in available_pdfs:
                            success = self.download_pdf(paper['pdf_url'], paper, session['name'])
                            if success:
                                pdf_downloaded += 1
                            time.sleep(1)  # Avoid too frequent requests
                        
                        self.logger.info(f"✅ Session completed: {len(papers)} papers, {len(available_pdfs)} available PDFs, {pdf_downloaded} downloaded successfully")
                    else:
                        self.logger.info(f"⚠️ Session {session['prefix']} found no papers")
                    
                    all_sessions_data.append({
                        'session_info': session,
                        'papers': papers,
                        'paper_count': len(papers)
                    })
                    
                    time.sleep(2)  # Rest between sessions
                    
                except Exception as e:
                    self.logger.error(f"❌ Error processing session {session['name']}: {e}")
                    self.stats['errors'] += 1
                    continue
            
            # Create final report
            self.create_final_summary(all_sessions_data)
            
            elapsed_time = time.time() - start_time
            self.logger.info(f"\n🎉 Scraping completed! Time elapsed: {elapsed_time:.2f} seconds")
            self.logger.info(f"📊 Final statistics:")
            self.logger.info(f"  ✅ Sessions processed: {self.stats['sessions_processed']}")
            self.logger.info(f"  📄 Total papers: {self.stats['total_papers']}")
            self.logger.info(f"  💾 PDFs downloaded: {self.stats['downloaded_pdfs']}")
            self.logger.info(f"  ❌ Errors: {self.stats['errors']}")
            
            return all_sessions_data
            
        except Exception as e:
            self.logger.error(f"Critical error during scraping process: {e}")
            raise


def main():
    """Main function to run the MEDSI2025 scraper."""
    print("MEDSI2025 Conference Web Scraper")
    print("=" * 60)
    print("Comprehensive scraper for MEDSI2025 conference papers")
    print("Author: Ming Liu")
    print()
    
    scraper = MEDSI2025Scraper()
    
    try:
        print("Starting test mode...")
        results = scraper.run(test_mode=True)
        
        print("\n" + "="*60)
        print("Test completed successfully!")
        
        # Ask if user wants to continue with full scraping
        print("\nWould you like to continue with full scraping of all 16 sessions?")
        choice = input("Enter 'y' to continue with full scraping, any other key to exit: ").lower().strip()
        
        if choice == 'y':
            print("\nStarting full scraping...")
            results = scraper.run(test_mode=False)
            
            print("\n" + "="*60)
            print("Full scraping completed successfully!")
            print(f"Output directory: {scraper.output_dir}")
            print("\nMain output files:")
            print("  📊 MEDSI2025_Final_Report.txt - Complete scraping report")
            print("  📈 MEDSI2025_All_Papers.csv - All papers Excel table")
            print("  🗂️ MEDSI2025_Complete_Index.json - Complete data index")
            print("  📁 Sessions/ - Session-categorized detailed data")
            print("  📄 PDFs/ - Downloaded PDF files (categorized by session)")
            print("  🔍 Debug/ - Debug information and page content")
            print("\n💡 Each session contains JSON, CSV, TXT format data")
        
    except KeyboardInterrupt:
        print("\n⏹️ User interrupted scraping")
    except Exception as e:
        print(f"\n❌ Scraping failed: {e}")


if __name__ == "__main__":
    main()