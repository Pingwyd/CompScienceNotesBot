#!/usr/bin/env python3
"""
Network Route Analyzer
Analyze network routes to identify bottlenecks and optimize paths

This tool:
- Traces routes to game servers
- Identifies high-latency hops
- Suggests optimization strategies
- Compares multiple routes

Usage:
    python route_analyzer.py
"""

import subprocess
import re
import sys
from collections import defaultdict

class RouteAnalyzer:
    """Analyze network routes to identify bottlenecks"""
    
    def __init__(self):
        self.routes = {}
    
    def traceroute(self, target, max_hops=30):
        """
        Perform traceroute to target
        Returns list of hops with latency
        
        Note: Traceroute shows CUMULATIVE latency from source to each hop.
        For example:
        - Hop 1: 5ms (5ms from source)
        - Hop 2: 15ms (15ms from source, so hop added 10ms)
        - Hop 3: 40ms (40ms from source, so hop added 25ms)
        
        To find bottleneck, calculate: hop[i] - hop[i-1]
        """
        print(f"\n🔍 Tracing route to {target}...")
        hops = []
        
        try:
            # Use appropriate command for OS
            if sys.platform == 'win32':
                cmd = ['tracert', '-h', str(max_hops), target]
            else:
                cmd = ['traceroute', '-m', str(max_hops), '-q', '1', target]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            # Parse traceroute output
            lines = result.stdout.split('\n')
            hop_num = 0
            
            for line in lines:
                # Look for hop patterns
                if sys.platform == 'win32':
                    # Windows: "  1    <1 ms    <1 ms    <1 ms  192.168.1.1"
                    match = re.search(r'^\s*(\d+)\s+(<?\d+)\s+ms', line)
                else:
                    # Linux: " 1  192.168.1.1 (192.168.1.1)  1.234 ms"
                    match = re.search(r'^\s*(\d+)\s+\S+.*?(\d+\.?\d*)\s+ms', line)
                
                if match:
                    hop_num = int(match.group(1))
                    latency = float(match.group(2).replace('<', ''))
                    
                    # Extract IP/hostname
                    ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
                    ip = ip_match.group(1) if ip_match else 'unknown'
                    
                    hops.append({
                        'hop': hop_num,
                        'ip': ip,
                        'latency': latency
                    })
            
            return hops
            
        except subprocess.TimeoutExpired:
            print("⚠️  Traceroute timed out")
            return []
        except Exception as e:
            print(f"❌ Error: {e}")
            return []
    
    def analyze_route(self, target):
        """Analyze route and identify issues"""
        hops = self.traceroute(target)
        
        if not hops:
            print(f"❌ Could not trace route to {target}")
            return None
        
        # Store route
        self.routes[target] = hops
        
        # Analysis
        total_hops = len(hops)
        # Traceroute shows cumulative latency, so total is the final hop's latency
        total_latency = hops[-1]['latency'] if hops else 0
        
        # Find bottlenecks (hops with high latency increase)
        # Traceroute latencies are cumulative, so diff = latency added by that hop
        bottlenecks = []
        for i in range(1, len(hops)):
            latency_increase = hops[i]['latency'] - hops[i-1]['latency']
            # Handle jitter (negative values) by taking absolute value
            # Only flag as bottleneck if consistently high (>20ms added)
            if latency_increase > 20:  # More than 20ms added by this hop
                bottlenecks.append({
                    'hop': hops[i]['hop'],
                    'ip': hops[i]['ip'],
                    'increase': latency_increase,
                    'total_latency': hops[i]['latency']
                })
        
        return {
            'target': target,
            'hops': hops,
            'total_hops': total_hops,
            'total_latency': total_latency,
            'bottlenecks': bottlenecks
        }
    
    def display_analysis(self, analysis):
        """Display route analysis results"""
        if not analysis:
            return
        
        print("\n" + "=" * 80)
        print(f"   ROUTE ANALYSIS: {analysis['target']}")
        print("=" * 80)
        
        # Route path
        print("\nRoute Path:")
        print("-" * 80)
        print(f"{'Hop':<5} {'IP Address':<20} {'Latency':<12} {'Status'}")
        print("-" * 80)
        
        for hop in analysis['hops']:
            # Determine status
            if hop['latency'] < 30:
                status = "🟢 Good"
            elif hop['latency'] < 50:
                status = "🟡 Fair"
            else:
                status = "🔴 High"
            
            print(f"{hop['hop']:<5} {hop['ip']:<20} {hop['latency']:>6.1f} ms    {status}")
        
        # Summary
        print("\n" + "=" * 80)
        print("Summary:")
        print("-" * 80)
        print(f"Total Hops:     {analysis['total_hops']}")
        print(f"Total Latency:  {analysis['total_latency']:.1f} ms")
        
        # Bottlenecks
        if analysis['bottlenecks']:
            print(f"\n⚠️  Bottlenecks Detected: {len(analysis['bottlenecks'])}")
            print("-" * 80)
            for b in analysis['bottlenecks']:
                print(f"Hop {b['hop']} ({b['ip']}): +{b['increase']:.1f} ms increase")
                print(f"  → Total latency at this hop: {b['total_latency']:.1f} ms")
        else:
            print("\n✅ No significant bottlenecks detected")
        
        # Recommendations
        print("\n" + "=" * 80)
        print("Recommendations:")
        print("-" * 80)
        
        if analysis['total_latency'] < 30:
            print("🟢 Excellent connection! No optimization needed.")
        elif analysis['total_latency'] < 50:
            print("🟡 Good connection, minor optimizations possible:")
            print("   • Use wired connection instead of WiFi")
            print("   • Close bandwidth-heavy applications")
        else:
            print("🔴 High latency detected. Consider:")
            print("   • Using a VPN with optimized routing")
            print("   • Choosing a server closer to your location")
            print("   • Contacting your ISP about routing issues")
        
        if analysis['bottlenecks']:
            print("\nBottleneck-specific suggestions:")
            for b in analysis['bottlenecks']:
                if b['hop'] <= 3:
                    print(f"   • Hop {b['hop']}: Local network issue - check router/modem")
                else:
                    print(f"   • Hop {b['hop']}: ISP routing issue - VPN may help")
    
    def compare_routes(self, targets):
        """Compare routes to multiple targets"""
        print("\n" + "=" * 80)
        print("   COMPARING ROUTES TO MULTIPLE SERVERS")
        print("=" * 80)
        
        analyses = []
        for target in targets:
            analysis = self.analyze_route(target)
            if analysis:
                analyses.append(analysis)
                self.display_analysis(analysis)
        
        # Comparison summary
        if len(analyses) > 1:
            print("\n" + "=" * 80)
            print("   COMPARISON SUMMARY")
            print("=" * 80)
            print(f"\n{'Server':<30} {'Hops':<8} {'Latency':<12} {'Bottlenecks'}")
            print("-" * 80)
            
            for a in analyses:
                print(f"{a['target']:<30} {a['total_hops']:<8} "
                      f"{a['total_latency']:>6.1f} ms    {len(a['bottlenecks'])}")
            
            # Find best server
            best = min(analyses, key=lambda x: x['total_latency'])
            print("\n" + "=" * 80)
            print(f"✨ BEST SERVER: {best['target']} ({best['total_latency']:.1f} ms)")
            print("=" * 80)


def main():
    """Main function"""
    print("=" * 80)
    print("   NETWORK ROUTE ANALYZER")
    print("   Identify bottlenecks and optimize network paths")
    print("=" * 80)
    
    analyzer = RouteAnalyzer()
    
    # Example servers (modify for your needs)
    print("\nExample servers for testing:")
    print("1. Google DNS (8.8.8.8)")
    print("2. Cloudflare DNS (1.1.1.1)")
    print("3. Custom server")
    
    print("\nSelect option (1-3): ", end='')
    choice = input().strip()
    
    targets = []
    
    if choice == '1':
        targets = ['8.8.8.8']
    elif choice == '2':
        targets = ['1.1.1.1']
    elif choice == '3':
        print("Enter server address (IP or hostname): ", end='')
        server = input().strip()
        if server:
            targets = [server]
        else:
            print("❌ No server provided")
            return
    else:
        print("❌ Invalid choice")
        return
    
    # Analyze routes
    if targets:
        print("\n⚠️  Note: Traceroute may take 30-60 seconds per server")
        print("⚠️  Some routers block traceroute - this is normal\n")
        
        analyzer.compare_routes(targets)
        
        print("\n" + "=" * 80)
        print("✅ Analysis complete!")
        print("=" * 80)


if __name__ == "__main__":
    main()
