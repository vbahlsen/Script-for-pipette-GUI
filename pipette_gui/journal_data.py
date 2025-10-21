from collections import defaultdict
import csv

class JournalData:
    def __init__(self):
        self.cases = defaultdict(list)
        self.total_samples = 0
        self.total_cases = 0
    
    def load_file(self, file_path):
        """Load data from either .txt or .csv file"""
        self.cases.clear()
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                if file_path.lower().endswith('.csv'):
                    # Try to read as CSV first
                    reader = csv.reader(f)
                    lines = [row[0] for row in reader if row]  # Assume first column
                else:
                    # Read as plain text
                    lines = [line.strip() for line in f if line.strip()]
                
            print(f"Journal data loaded: {len(lines)} entries")
            
            # Group samples by case ID
            for sample_id in lines:
                self.cases[sample_id].append(len(self.cases[sample_id]) + 1)
            
            self.total_cases = len(self.cases)
            self.total_samples = sum(len(samples) for samples in self.cases.values())
            
            print(f"Grouped into {self.total_cases} cases with {self.total_samples} total samples")
            for case_id, samples in self.cases.items():
                print(f"  Case {case_id}: {len(samples)} samples")
            
            return True
            
        except Exception as e:
            print(f"Error loading journal data: {e}")
            self.cases.clear()
            self.total_samples = 0
            self.total_cases = 0
            return False
    
    def get_individual_samples_count(self):
        """Returns the total number of individual samples (excluding pooled samples)"""
        return sum(len(samples) - 1 for samples in self.cases.values())
    
    def get_pooled_samples_count(self):
        """Returns the number of pooled samples (one per case)"""
        return len(self.cases)
    
    def get_case_sample_counts(self):
        """Returns a list of tuples (case_id, num_samples)"""
        return [(case_id, len(samples)) for case_id, samples in self.cases.items()]
    
    def get_sample_mapping(self):
        """Returns mapping of well positions to sample information"""
        individual_samples = []
        pooled_samples = []
        
        for case_id, sample_nums in self.cases.items():
            # Add individual samples (excluding the pool sample)
            for sample_num in sample_nums[:-1]:  # All but last
                individual_samples.append({
                    'case_id': case_id,
                    'sample_num': sample_num,
                    'is_pool': False
                })
            
            # Add pool sample
            pooled_samples.append({
                'case_id': case_id,
                'sample_num': len(sample_nums),  # Last number is pool
                'is_pool': True
            })
        
        result = {
            'individual': individual_samples,
            'pooled': pooled_samples
        }
        
        print(f"Created sample mapping with {len(individual_samples)} individual samples and {len(pooled_samples)} pooled samples")
        
        return result