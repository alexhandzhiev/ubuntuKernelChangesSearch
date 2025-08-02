#!/usr/bin/env python3
"""
Ubuntu Kernel CHANGES Search Script
Searches through all CHANGES files in Ubuntu mainline kernel directories
for lines containing specified patterns (e.g., mt79*, power management, etc.)
"""

import requests
import re
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import argparse
from typing import List, Dict, Tuple

class KernelChangesSearcher:
    def __init__(self, base_url: str = "https://kernel.ubuntu.com/~kernel-ppa/mainline/"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
        })
        
    def get_kernel_directories(self) -> List[str]:
        """Get all kernel version directories from the mainline page"""
        try:
            response = self.session.get(self.base_url, timeout=10)
            response.raise_for_status()
            
            # Extract directory links (folders ending with /)
            dir_pattern = r'href="(v[\d\.]+-?(?:rc\d+)?/)"'
            directories = re.findall(dir_pattern, response.text)
            
            # Sort directories by version
            def version_key(d):
                # Extract version numbers for sorting
                version = d.strip('v/')
                parts = version.replace('-rc', '.rc').split('.')
                return [int(p.replace('rc', '')) if p.replace('rc', '').isdigit() else 999 for p in parts]
            
            directories.sort(key=version_key, reverse=True)
            print(f"Found {len(directories)} kernel directories")
            return directories
            
        except Exception as e:
            print(f"Error fetching directories: {e}")
            return []
    
    def search_changes_file(self, directory: str, search_patterns: List[str]) -> List[Tuple[str, str, str]]:
        """Search CHANGES file in a specific directory for patterns"""
        changes_url = urljoin(self.base_url, f"{directory}CHANGES")
        results = []
        
        try:
            response = self.session.get(changes_url, timeout=10)
            if response.status_code == 404:
                return results
            
            response.raise_for_status()
            content = response.text
            
            lines = content.split('\n')
            for line_num, line in enumerate(lines, 1):
                line_lower = line.lower()
                for pattern in search_patterns:
                    # Support wildcards with regex
                    regex_pattern = pattern.replace('*', '.*').lower()
                    if re.search(regex_pattern, line_lower):
                        results.append((directory.strip('/'), line.strip(), str(line_num)))
                        break  # Don't duplicate the same line for multiple patterns
            
        except requests.RequestException as e:
            print(f"Error fetching {changes_url}: {e}")
        except Exception as e:
            print(f"Error processing {directory}: {e}")
            
        return results
    
    def search_all_changes(self, search_patterns: List[str], max_workers: int = 10) -> Dict[str, List[Tuple[str, str]]]:
        """Search all CHANGES files concurrently"""
        directories = self.get_kernel_directories()
        if not directories:
            return {}
        
        results = {}
        processed = 0
        
        print(f"Searching {len(directories)} directories for patterns: {search_patterns}")
        print("This may take several minutes...")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_dir = {
                executor.submit(self.search_changes_file, directory, search_patterns): directory 
                for directory in directories
            }
            
            # Process completed tasks
            for future in as_completed(future_to_dir):
                directory = future_to_dir[future]
                processed += 1
                
                try:
                    matches = future.result()
                    if matches:
                        for version, line, line_num in matches:
                            if version not in results:
                                results[version] = []
                            results[version].append((line, line_num))
                    
                    # Progress indicator
                    if processed % 20 == 0:
                        print(f"Processed {processed}/{len(directories)} directories...")
                        
                except Exception as e:
                    print(f"Error processing {directory}: {e}")
        
        print(f"Search complete! Processed {processed} directories")
        return results
    
    def print_results(self, results: Dict[str, List[Tuple[str, str]]], search_patterns: List[str]):
        """Print search results in a readable format"""
        if not results:
            print(f"\nNo matches found for patterns: {search_patterns}")
            return
        
        print(f"\n{'='*80}")
        print(f"SEARCH RESULTS for patterns: {search_patterns}")
        print(f"{'='*80}")
        
        # Sort by version (newest first)
        def version_key(version):
            parts = version.replace('v', '').replace('-rc', '.rc').split('.')
            return [int(p.replace('rc', '')) if p.replace('rc', '').isdigit() else 999 for p in parts]
        
        sorted_versions = sorted(results.keys(), key=version_key, reverse=True)
        
        total_matches = sum(len(matches) for matches in results.values())
        print(f"Found {total_matches} matches in {len(results)} kernel versions\n")
        
        for version in sorted_versions:
            matches = results[version]
            print(f"\n📁 Kernel Version: {version}")
            print(f"   URL: https://kernel.ubuntu.com/~kernel-ppa/mainline/{version}/CHANGES")
            print(f"   Matches: {len(matches)}")
            print("-" * 60)
            
            for line, line_num in matches:
                # Highlight the matching pattern
                highlighted_line = line
                for pattern in search_patterns:
                    regex_pattern = pattern.replace('*', '.*')
                    highlighted_line = re.sub(
                        f'({regex_pattern})', 
                        r'🔍 \1 🔍', 
                        highlighted_line, 
                        flags=re.IGNORECASE
                    )
                
                print(f"   Line {line_num}: {highlighted_line}")
        
        print(f"\n{'='*80}")

def main():
    parser = argparse.ArgumentParser(
        description="Search Ubuntu mainline kernel CHANGES files for specific patterns",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python kernel_search.py mt79*
  python kernel_search.py mt7921 mt7922 power
  python kernel_search.py "transmission power" "wifi.*power"
  python kernel_search.py --max-workers 5 mt79*
        """
    )
    
    parser.add_argument(
        'patterns', 
        nargs='+', 
        help='Search patterns (supports wildcards with *)'
    )
    
    parser.add_argument(
        '--max-workers', 
        type=int, 
        default=10,
        help='Maximum number of concurrent downloads (default: 10)'
    )
    
    parser.add_argument(
        '--output', 
        help='Save results to file (optional)'
    )
    
    args = parser.parse_args()
    
    # Initialize searcher
    searcher = KernelChangesSearcher()
    
    # Perform search
    start_time = time.time()
    results = searcher.search_all_changes(args.patterns, args.max_workers)
    end_time = time.time()
    
    # Print results
    searcher.print_results(results, args.patterns)
    
    print(f"\nSearch completed in {end_time - start_time:.2f} seconds")
    
    # Save to file if requested
    if args.output:
        try:
            with open(args.output, 'w') as f:
                f.write(f"Ubuntu Kernel CHANGES Search Results\n")
                f.write(f"Search patterns: {args.patterns}\n")
                f.write(f"Search date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("="*80 + "\n\n")
                
                if results:
                    for version in sorted(results.keys(), reverse=True):
                        matches = results[version]
                        f.write(f"Kernel Version: {version}\n")
                        f.write(f"URL: https://kernel.ubuntu.com/~kernel-ppa/mainline/{version}/CHANGES\n")
                        f.write(f"Matches: {len(matches)}\n")
                        f.write("-" * 60 + "\n")
                        
                        for line, line_num in matches:
                            f.write(f"Line {line_num}: {line}\n")
                        f.write("\n")
                else:
                    f.write("No matches found.\n")
            
            print(f"Results saved to: {args.output}")
        except Exception as e:
            print(f"Error saving to file: {e}")

if __name__ == "__main__":
    main()