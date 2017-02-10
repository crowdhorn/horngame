import sys, os, traceback, itertools
from os import walk
import json
import subprocess32 as subprocess
from threading import Timer
import sh
import logging

# Logger
formatter = logging.Formatter('%(levelname)s - %(message)s')
handler = logging.StreamHandler(sys.stdout)
log = logging.getLogger()
log.addHandler(handler)


formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler = logging.FileHandler('/tmp/horngame.tool.log')
handler.setLevel(logging.DEBUG)
handler.setFormatter(formatter)
log = logging.getLogger()
log.setLevel(logging.DEBUG)
log.addHandler(handler)

#name of subfolder in app/static
SMT_DIR_SUFFIX = "smt_files"
PROBLEM_DIR_SUFFIX = "problem_files"

PRINCESS_PATH = os.path.join(sh.ELDARICA_PATH, "solver")
princess_command = os.path.join(PRINCESS_PATH, "princess")
eldarica_command = os.path.join(sh.ELDARICA_PATH, "eld")

task_id_key = "task_id"
problem_id_key = "problem_id"
clauses_key = "clauses"
violated_clause_key = "violated_clause"
instantiated_clause_key = "instantiated_clause"
predicate_key = "preds"

"""
creates a pri file to check with princess if the user provided 
predicates make all clauses valid.
"""
def create_princess_file(sol_dir, solution, out_file_name):
  lines = list()
  lines.append("\\predicates {")
  #TODO IsOdd(int, int);  
  for pred in solution[predicate_key]:    
    #conj with &
    type_sig=""
    comma = ""
    for arg in pred["args"]:
      type_sig+=comma
      comma = ", "
      type_sig+="int"
    lines.append("  {}({});".format(pred["name"], type_sig))
  lines.append("}")

  lines.append("\\problem {")
  prefix = ""
  for pred in solution[predicate_key]:
    arguement_string = ""
    comma = ""
    for arg in pred["args"]:
      arguement_string+=comma
      comma = ", "
      arguement_string+=arg      
      prefix+="\\forall int {}; ".format(arg)
    prefix += "({}({}) <-> {})".format(pred["name"], arguement_string, pred["assignment"])
  lines.append(prefix)  
  #TODO \forall int v0, v1; (IsOdd(v0, v1) <->
  #  (v0 >= 0 & 1 >= v1 & v1 >= 0))
  lines.append("->")

  task = load_task(sol_dir, solution[task_id_key])
  conj = ""
  for clause in task[clauses_key]:
    lines.append(conj + clause)
    conj = "& "
  #  \forall int v0; \forall int v1; (v1 >= 2 | -1 >= v1 | 0 >= v0 | IsOdd(1 + v0, v1))

  lines.append("}")

  with open(out_file_name, "w") as princess_file:
    princess_file.write("\n".join(lines))
  pass


def load_task(sol_dir, task_id):
  task_file_name = "task_{0}.json".format(task_id)
  data = dict()
  with open(os.path.join(sol_dir, task_file_name)) as data_file:    
    data = json.load(data_file)
  return data

def load_problem(sol_dir, problem_id):
  problem_file_name = "problem_{0}.json".format(problem_id)
  data = dict()
  with open(os.path.join(sol_dir, problem_file_name)) as data_file:    
    data = json.load(data_file)
  return data


def run_cmd(cmd, print_output=False, timeout=None):
  def kill_proc(proc, stats):
    stats['timed_out'] = True
    proc.kill()

  stats = {'timed_out': False,
           'output': ''}
  timer = None

  if print_output:
    print ("Running %s" % ' '.join(cmd))
    log.info("Running %s", ' '.join(cmd))
  try:
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    if timeout:
      timer = Timer(timeout, kill_proc, [process, stats])
      timer.start()

    for line in iter(process.stdout.readline, b''):
      stats['output'] = stats['output'] + line
      if print_output:
        log.info(line)
        sys.stdout.write(line)
        sys.stdout.flush()
    process.stdout.close()
    process.wait()
    stats['return_code'] = process.returncode
    if timer:
      timer.cancel()

  except:
    log.error("calling %s failed\n%s",' '.join(cmd),traceback.format_exc())
    print ('calling {cmd} failed\n{trace}'.format(cmd=' '.join(cmd),trace=traceback.format_exc()))
  return stats
