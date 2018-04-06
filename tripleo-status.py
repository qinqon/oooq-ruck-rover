#!/bin/env python
import requests
import re
import pprint
import json
import irc.client
import itertools
import sys
import feedparser

from bs4 import BeautifulSoup
from datetime import datetime 
from launchpadlib.launchpad import Launchpad

infra_status_regexp = re.compile('^ *([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}) *UTC *(.+)$')
failing_check_jobs = re.compile('^FAILING CHECK JOBS: .*')
sova_status_table = re.compile('.*arrayToDataTable\((\[.*\])\);.*', re.DOTALL)
sova_overall_job_name = re.compile('.*.*function (.*)_overall.*')

infra_status_url = 'https://wiki.openstack.org/wiki/Infrastructure_Status'
upstream_zuul_url = 'http://zuul.openstack.org/status'
rechecks_url = 'http://status.openstack.org/elastic-recheck/data/all.json'
sova_gate_status_url = 'http://cistatus.tripleo.org/gates/'

infra_status_utc_format = '%Y-%m-%d %H:%M:%S'

cachedir = "/home/ellorent/.launchpadlib/cache/"

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

def get_upstream_tripleo_gate():
    upstream_zuul = json.loads(requests.get(upstream_zuul_url).content) 
    gate_queues = next(pipeline['change_queues'] for pipeline in upstream_zuul['pipelines'] if pipeline['name'] == 'gate')
    tripleo_heads = next(queue for queue in gate_queues if queue['name'] == 'tripleo')['heads']
    tripleo_queue = []
    if tripleo_heads:
        tripleo_queue = [0]
    return tripleo_queue

def get_upstream_tripleo_bugs(since):
    launchpad = Launchpad.login_anonymously('OOOQ Ruck Rover', 'production', cachedir, version='devel')
    project = launchpad.projects['tripleo']

    # We can filter by status too 
    bugs = project.searchTasks(created_since = since)
    
    return bugs
    #browsed_bugs = []
    #for bug in bugs:
    #    browser = launchpad._browser
    #    browsed_bugs.append(browser.get(bug.self_link))
    #return browsed_bugs

def get_irc_gate_status():
    client = irc.client.Reactor()
    server = client.server()
    failing_jobs = [""]

    def on_connect(connection, event):
        connection.join('#oooq')
    
    def on_join(connection, event):
        connection.privmsg('#oooq', '!gatestatus')

    def on_disconmnect(connection, event):
        raise SystemExit()
    
    def on_public_message(connection, event):
        message = event.arguments[0]
        # TODO: Check it's hubbot
        if failing_check_jobs.match(message):
            failing_jobs[0] = message
            connection.quit("Using irc.client.py")

    try:
        server.connect("chat.freenode.net", 6667, "ruck-rover-bot")
    except irc.client.ServerConnectionError:
        print(sys.exc_info()[1])
        raise SystemExit(1)
    
    client.add_global_handler("welcome", on_connect)
    client.add_global_handler("join", on_join)
    client.add_global_handler("disconnect", on_disconmnect)
    client.add_global_handler("pubmsg", on_public_message)

    try:
        client.process_forever()
    except SystemExit:
        print('END')

    return failing_jobs[0]

def get_gate_failures(since):
    # TODO: Filter by since
    return feedparser.parse('http://www.rssmix.com/u/8262477/rss.xml')

def get_top_tripleo_rechecks():
    limit=5
    affected_project='tripleo'
    rechecks = json.loads(requests.get(rechecks_url).content)['buglist'][:limit]
    for recheck in rechecks:
        del recheck['data']
    return [recheck for recheck in rechecks if affected_project in recheck['bug_data']['affects']]

def get_sova_gate_status():
    sova_gate_status = requests.get(sova_gate_status_url) 
    sova_gate_status_soup = BeautifulSoup(sova_gate_status.content, 'html.parser')
    scripts = sova_gate_status_soup.find_all('script')
    sova_status = {}
    for script in scripts:
        if 'ci_overall' in script.get_text():
            ci_overall = eval((re.findall(sova_status_table, script.string)[0]))
            sova_status['master-ci-overall'] = ci_overall
        elif '_overall' in script.get_text():
            print(script.string)
            job_name = re.findall(sova_overall_job_name, script.string)[0]
            job_status = eval((re.findall(sova_status_table, script.string)[0]))
            sova_status[job_name] = ci_overall
    return sova_status
 
def filter_infra_issues_by_date(date):
    issues = get_infra_issues()
    search_result = [(ts, issue) for ts, issue in issues if ts > date]
    return search_result

# TODO: Use pandas to simplify rendering and filtering
# TODO: Parallelize gathering of information
def main():
    since_date=datetime(2018, 3, 13)
    status = {}
#    status['infra-issues'] = filter_infra_issues_by_date(since_date)
#    status['upstream-tripleo-gate'] = get_upstream_tripleo_gate()
#    status['upstream-tripleo-bugs'] = get_upstream_tripleo_bugs(since=since_date)
#    status['gate-status'] = get_irc_gate_status()
#    status['gate-failures'] = get_gate_failures(since=since_date)
#    status['top-tripleo-rechecks'] = get_top_tripleo_rechecks()
    status['sova-gate-status'] = get_sova_gate_status()
    
#    print("---")
#    print("--- TripleO gate queue ---")
#    print("---")
#    print("Number of infra issues: {}".format(len(status['infra-issues'])))
#    print("Size of tripleo gate queue: {}".format(len(status['upstream-tripleo-gate'])))
#    #TODO: Check queue time")
#    print("")
#    print("---")
#    print("--- New bugs ---")
#    print("---")
#    print("Number of tripleo bugs: {}".format(len(status['upstream-tripleo-bugs'])))
#    print("Gate status: {}".format(status['gate-status']))
#    #TODO: Check #tripleo for <ooolpbot> URGENT TRIPLEO TASKS NEED ATTENTION")
#    print("Number of gate failures: {}".format(len(status['gate-failures'])))
#    print("---")
#    print("--- Promotion branches ---")
#    print("---")
#    print("TODO")
#    print("---")
#    print("--- Upstream Health ---")
#    print("---")
#    print("Number of tripleo rechecks: {}".format(len(status['top-tripleo-rechecks'])))
    print("Sova gate status: {}".format(status['sova-gate-status']))

if __name__ == '__main__':
    main()
