import sys, os, traceback, itertools, tempfile
from os import walk
import json
import subprocess32 as subprocess
from contextlib import contextmanager
import logging


sys.path.append("./horngame/tool")
import problems
import common

horn_repos = [ {"url":"git@github.com:crowdhorn/demo_clauses.git", "folders":["demo_clauses/handwritten"]},
               {"url":"git@github.com:crowdhorn/sv-benchmarks.git", "folders":["sv-benchmarks/clauses/ALIA/dillig"]},
               {"url":"git@github.com:crowdhorn/sv-benchmarks.git", "folders":["sv-benchmarks/clauses/LIA/Eldarica/RECUR"]},
               {"url":"git@github.com:crowdhorn/sv-benchmarks.git", "folders":["sv-benchmarks/clauses/QALIA"]}
             ]

# horn_repos = [{"url":"git@github.com:crowdhorn/demo_clauses.git", "folders":["demo_clauses/handwritten"]}]

def bulk_import_smt_files():
  formatter = logging.Formatter('%(levelname)s - %(message)s')
  handler = logging.StreamHandler(sys.stdout)
  log = logging.getLogger()
  log.addHandler(handler)


  smt_file_names = fetch_smt_file_from_repos()
  if len(smt_file_names) == 0:
    print ("No clauses found :(")
    return
  with cd("horngame"):
    problem_dir = os.path.join("static", common.PROBLEM_DIR_SUFFIX)
    if not os.path.exists(problem_dir):
      os.makedirs(problem_dir)

    problems.generate_problem_file(smt_file_names, problem_dir)

def fetch_smt_file_from_repos():
  temp_dir = "./tmp_smt2"
  if not os.path.exists(temp_dir):
    os.makedirs(temp_dir)
  smt_file_names = []
  with cd(temp_dir):
    for repo in horn_repos:      
      if os.path.isdir(repo["folders"][0]):
        common.log.info("Using existing clone of {}. Delete if you don't like that.".format(repo["url"]))
      else:
        cmd = ["git", "clone", repo["url"]]
        run_cmd(cmd, True)
      for folder in repo["folders"]:
        for dirpath, _ , filenames in os.walk(folder):
          for f in filenames:
            if f.endswith(".smt2"):
              smt_file_names += [os.path.abspath(os.path.join(dirpath, f))]
  return smt_file_names            

@contextmanager
def cd(newdir):
  prevdir = os.getcwd()
  os.chdir(os.path.expanduser(newdir))
  try:
    yield
  finally:
    os.chdir(prevdir)


def run_cmd(cmd, print_output=False, timeout=None):
  def kill_proc(proc, stats):
    stats['timed_out'] = True
    proc.kill()

  stats = {'timed_out': False,
           'output': ''}
  timer = None

  if print_output:
    print ("Running %s" % ' '.join(cmd))
  try:
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    if timeout:
      timer = Timer(timeout, kill_proc, [process, stats])
      timer.start()

    for line in iter(process.stdout.readline, b''):
      stats['output'] = stats['output'] + line
      if print_output:
        sys.stdout.write(line)
        sys.stdout.flush()
    process.stdout.close()
    process.wait()
    stats['return_code'] = process.returncode
    if timer:
      timer.cancel()

  except:
    print ('calling {cmd} failed\n{trace}'.format(cmd=' '.join(cmd),trace=traceback.format_exc()))
  return stats


if __name__ == "__main__": 
  bulk_import_smt_files()  
