#!/usr/bin/env python3

import polars as pl
from init import read_vault

hosts_query = """
SELECT 
    vm_name,
    ipv4,
    svc,
    env,
    os
FROM
    hosts
"""

def main():
    creds = read_vault('tracepoint-a', 'access/db')
    conn_str = creds['conn_str']
    
    


if __name__ == '__main__':
    main()