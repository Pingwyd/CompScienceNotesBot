#!/usr/bin/env python3
"""
Ping Monitoring and Optimization Tool
Educational example for understanding network latency

This tool demonstrates:
- Multi-server ping monitoring
- Latency tracking and analysis
- Automatic best server selection
- Real-time statistics

Usage:
    python ping_monitor.py
"""

import subprocess
import re
import time
import statistics
from datetime import datetime
from collections import defaultdict
import sys

class PingMonitor:
    """
    Monitor network latency to multiple servers
    """
    
    def __init__(self):
        self.servers = []
        self.history = defaultdict(list)
        self.max_history = 60  # Keep last 60 measurements
    
    def add_server(self, name, address):
        """Add a server to monitor"""
        self.servers.append({'name': name, 'address': address})
        print(f"✓ Added server: {name} ({address})")
    
    def ping(self, address, count=1, timeout=2):
        """
        Ping a server and return latency in milliseconds
        Returns None if ping fails
        """
        try:
            # Adjust ping command for different OS
            if sys.platform == 'win32':
                cmd = ['ping', '-n', str(count), '-w', str(timeout * 1000), address]
                pattern = r'Average = (\d+)ms'
            else:  # Linux/Mac
                cmd = ['ping', '-c', str(count), '-W', str(timeout), address]
                pattern = r'avg.*?= [\d.]+/([\d.]+)/'
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout + 1
            )
            
            # Parse latency from output
            match = re.search(pattern, result.stdout)
            if match:
                return float(match.group(1))
            
            return None
            
        except (subprocess.TimeoutExpired, Exception) as e:
            return None
    
    def get_status_indicator(self, latency):
        """Return emoji status based on latency"""
        if latency is None:
            return "❌", "TIMEOUT"
        elif latency < 30:
            return "🟢", "EXCELLENT"
        elif latency < 50:
            return "🟡", "GOOD"
        elif latency < 100:
            return "🟠", "FAIR"
        else:
            return "🔴", "POOR"
    
    def monitor_once(self):
        """Perform one round of monitoring"""
        results = []
        
        for server in self.servers:
            latency = self.ping(server['address'])
            
            # Store in history
            self.history[server['name']].append(latency)
            
            # Keep history limited
            if len(self.history[server['name']]) > self.max_history:
                self.history[server['name']].pop(0)
            
            results.append({
                'name': server['name'],
                'address': server['address'],
                'latency': latency
            })
        
        return results
    
    def get_statistics(self, server_name):
        """Calculate statistics for a server"""
        data = [x for x in self.history[server_name] if x is not None]
        
        if not data:
            return None
        
        return {
            'avg': statistics.mean(data),
            'min': min(data),
            'max': max(data),
            'stdev': statistics.stdev(data) if len(data) > 1 else 0,
            'samples': len(data)
        }
    
    def find_best_server(self):
        """Find server with lowest average latency"""
        best = None
        best_avg = float('inf')
        
        for server in self.servers:
            stats = self.get_statistics(server['name'])
            if stats and stats['avg'] < best_avg:
                best_avg = stats['avg']
                best = server
        
        return best, best_avg
    
    def display_results(self, results):
        """Display monitoring results"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Clear screen (cross-platform)
        print('\033[2J\033[H' if sys.platform != 'win32' else '\n' * 50)
        
        print("=" * 80)
        print(f"   PING MONITORING TOOL - {timestamp}")
        print("=" * 80)
        print()
        
        # Current results
        print("Current Latency:")
        print("-" * 80)
        for result in results:
            emoji, status = self.get_status_indicator(result['latency'])
            latency_str = f"{result['latency']:.1f} ms" if result['latency'] else "TIMEOUT"
            
            print(f"{emoji} {result['name']:25} {latency_str:>12}  [{status}]")
        
        print()
        
        # Statistics
        print("Statistics (Last 60 samples):")
        print("-" * 80)
        print(f"{'Server':<25} {'Avg':>8} {'Min':>8} {'Max':>8} {'Jitter':>8} {'Loss':>6}")
        print("-" * 80)
        
        for server in self.servers:
            stats = self.get_statistics(server['name'])
            if stats:
                # Calculate packet loss
                total = len(self.history[server['name']])
                lost = sum(1 for x in self.history[server['name']] if x is None)
                loss_pct = (lost / total * 100) if total > 0 else 0
                
                print(f"{server['name']:<25} "
                      f"{stats['avg']:>7.1f}  "
                      f"{stats['min']:>7.1f}  "
                      f"{stats['max']:>7.1f}  "
                      f"{stats['stdev']:>7.1f}  "
                      f"{loss_pct:>5.1f}%")
        
        print()
        
        # Best server recommendation
        best, best_avg = self.find_best_server()
        if best:
            print("=" * 80)
            print(f"✨ RECOMMENDED SERVER: {best['name']} ({best_avg:.1f} ms average)")
            print("=" * 80)
    
    def monitor_continuous(self, interval=2):
        """Continuously monitor servers"""
        print("\n🚀 Starting continuous monitoring...")
        print(f"   Interval: {interval} seconds")
        print("   Press Ctrl+C to stop\n")
        
        try:
            while True:
                results = self.monitor_once()
                self.display_results(results)
                time.sleep(interval)
        
        except KeyboardInterrupt:
            print("\n\n⏹️  Monitoring stopped by user")
            self.show_summary()
    
    def show_summary(self):
        """Show final summary"""
        print("\n" + "=" * 80)
        print("   MONITORING SUMMARY")
        print("=" * 80)
        
        for server in self.servers:
            stats = self.get_statistics(server['name'])
            if stats:
                print(f"\n{server['name']} ({server['address']}):")
                print(f"  Average Latency: {stats['avg']:.1f} ms")
                print(f"  Min: {stats['min']:.1f} ms, Max: {stats['max']:.1f} ms")
                print(f"  Jitter (StdDev): {stats['stdev']:.1f} ms")
                print(f"  Samples: {stats['samples']}")


def main():
    """Main function"""
    print("=" * 80)
    print("   PING MONITORING AND OPTIMIZATION TOOL")
    print("   Educational Example for Network Latency Analysis")
    print("=" * 80)
    print()
    
    # Create monitor
    monitor = PingMonitor()
    
    # Add some example servers
    # You can modify these to test your actual game servers
    print("Adding servers to monitor...")
    monitor.add_server("Google DNS", "8.8.8.8")
    monitor.add_server("Cloudflare DNS", "1.1.1.1")
    monitor.add_server("OpenDNS", "208.67.222.222")
    
    # Ask user if they want to add custom servers
    print("\nWould you like to add custom servers? (y/n): ", end='')
    if input().lower() == 'y':
        while True:
            print("\nEnter server name (or press Enter to finish): ", end='')
            name = input().strip()
            if not name:
                break
            
            print("Enter server address (IP or hostname): ", end='')
            address = input().strip()
            if address:
                monitor.add_server(name, address)
    
    print("\n" + "=" * 80)
    print("Starting monitoring in 3 seconds...")
    print("=" * 80)
    time.sleep(3)
    
    # Start continuous monitoring
    monitor.monitor_continuous(interval=2)


if __name__ == "__main__":
    main()
