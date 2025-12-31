import csv
import random
from datetime import datetime, timedelta

with open('data/test_case_11/large_dataset.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['id', 'name', 'email', 'created_at', 'value'])
    
    for i in range(100000):  # 100K records
        writer.writerow([
            i,
            f"User_{i}",
            f"user{i}@example.com",
            (datetime.now() - timedelta(days=random.randint(0, 365))).isoformat(),
            round(random.uniform(10.0, 1000.0), 2)
        ])
