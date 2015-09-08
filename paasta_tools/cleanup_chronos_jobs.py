#!/usr/bin/env python

"""
Usage: ./cleanup_chronos_jobs.py [options]

Clean up chronos jobs that aren't supposed to run on this cluster by deleting them.

Gets the current job list from chronos, and then a 'valid_job_list'
via chronos_tools.get_chronos_jobs_for_cluster

If a job is deployed by chronos but not in the expected list, it is deleted.
Any tasks associated with that job are also deleted.

- -d <SOA_DIR>, --soa-dir <SOA_DIR>: Specify a SOA config dir to read from
"""

import argparse
import sys

import service_configuration_lib

from paasta_tools import chronos_tools


def parse_args():
    parser = argparse.ArgumentParser(description='Cleans up stale chronos jobs.')
    parser.add_argument('-d', '--soa-dir', dest="soa_dir", metavar="SOA_DIR",
                        default=service_configuration_lib.DEFAULT_SOA_DIR,
                        help="define a different soa config directory")
    args = parser.parse_args()
    return args


def execute_chronos_api_call_for_job(api_call, job):
    """Attempt a call to the Chronos api, catching any exception.

    We *have* to catch Exception, because the client catches
    the more specific exception thrown by the http clients
    and rethrows an Exception -_-.

    The chronos api returns a 204 No Content when the delete is
    successful, and chronos-python only returns the body of the
    response from all http calls. So, if this is successful,
    then None will be returned.
    https://github.com/asher/chronos-python/pull/7

    We catch it here, so that the other deletes are completed.
    """
    try:
        return api_call(job)
    except Exception as e:
        return e


def cleanup_jobs(client, jobs):
    """Maps a list of jobs to cleanup to a list of response objects (or exception objects) from the api"""
    return [(job, execute_chronos_api_call_for_job(client.delete, job)) for job in jobs]


def cleanup_tasks(client, jobs):
    """Maps a list of tasks to cleanup to a list of response objects (or exception objects) from the api"""
    return [(job, execute_chronos_api_call_for_job(client.delete_tasks, job)) for job in jobs]


def jobs_to_delete(expected_jobs, actual_jobs):
    return list(set(actual_jobs).difference(set(expected_jobs)))


def format_list_output(title, job_names):
    return '%s\n  %s' % (title, '\n  '.join(job_names))


def running_job_names(client):
    return [job['name'] for job in client.list()]


def expected_job_names(service_job_pairs):
    """
    Expects a list of pairs in the form (service_name, job_name)
    and returns the list of pairs mapped to the job name of each pair.
    """
    return [job[-1] for job in service_job_pairs]


def main():
    args = parse_args()
    soa_dir = args.soa_dir

    config = chronos_tools.load_chronos_config()
    client = chronos_tools.get_chronos_client(config)

    # get_chronos_jobs_for_cluster returns (service_name, job)
    expected_jobs = expected_job_names(chronos_tools.get_chronos_jobs_for_cluster(soa_dir=soa_dir))
    running_jobs = running_job_names(client)

    to_delete = jobs_to_delete(expected_jobs, running_jobs)

    task_responses = cleanup_tasks(client, to_delete)
    task_successes = []
    task_failures = []
    for response in task_responses:
        if isinstance(response[-1], Exception):
            task_failures.append(response)
        else:
            task_successes.append(response)

    job_responses = cleanup_jobs(client, to_delete)
    job_successes = []
    job_failures = []
    for response in job_responses:
        if isinstance(response[-1], Exception):
            job_failures.append(response)
        else:
            job_successes.append(response)

    if len(to_delete) == 0:
        print 'No Chronos Jobs to remove'
    else:
        if len(task_successes) > 0:
            print format_list_output("Successfully Removed Tasks (if any were running) for:",
                                     [job[0] for job in task_successes])

        # if there are any failures, print and exit appropriately
        if len(task_failures) > 0:
            print format_list_output("Failed to Delete Tasks for:", [job[0] for job in task_failures])

        if len(job_successes) > 0:
            print format_list_output("Successfully Removed Jobs:", [job[0] for job in job_successes])

        # if there are any failures, print and exit appropriately
        if len(job_failures) > 0:
            print format_list_output("Failed to Delete Jobs:", [job[0] for job in job_failures])

        if len(job_failures) > 0 or len(task_failures) > 0:
            sys.exit(1)

if __name__ == "__main__":
    main()