#!/bin/env python
import requests
import re
import pprint
from bs4 import BeautifulSoup
from datetime import datetime 

infra_status_regexp = re.compile('^ *([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}) *UTC *(.+)$')
infra_status_url = 'https://wiki.openstack.org/wiki/Infrastructure_Status'
infra_status_utc_format = '%Y-%m-%d %H:%M:%S'

def get_infra_issues():
    infra_status = requests.get(infra_status_url) 
    infra_status_soup = BeautifulSoup(infra_status.content, 'html.parser')
    raw_issues = infra_status_soup.find_all('li')
    issues = []
    for ts_and_issue in raw_issues:
        m = infra_status_regexp.match(ts_and_issue.get_text())
        if m:
            ts = datetime.strptime(m.group(1), infra_status_utc_format)
            issue = m.group(2)
            issues.append((ts, issue))
    return issues

def filter_infra_issues_by_date(date):
    issues = get_infra_issues()
    search_result = [(ts, issue) for ts, issue in issues if ts > date]
    return search_result

def main():
    filtered_issues = filter_infra_issues_by_date(datetime(2018, 3, 13))
    pp = pprint.PrettyPrinter(indent=4)
    pp.pprint(filtered_issues)

if __name__ == '__main__':
    main()
