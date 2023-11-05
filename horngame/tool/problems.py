import sys, os, traceback, itertools
from os import walk
import json
import subprocess32 as subprocess
from shutil import copyfile

import hashlib as h

from common import *
import uuid

MAX_TASKS_PER_PROBLEM = 20

TOTAL_SMT = 0
TOTAL_PROBLEM = 0 
TOTAL_TASK = 0
TOTAL_NO_TASK = 0


from haikunator import Haikunator
haikunator = Haikunator()

"""
Check if the conjunction of the set
of clauses is already unsat. If so, 
we have to drop the task because the
user would never find a solution.
"""
def check_solvable(task):
  lines = list()
  lines.append("\\predicates {")
  #TODO IsOdd(int, int);  
  for pred in task[predicate_key]:    
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
  conj = ""
  for clause in task[clauses_key]:
    lines.append(conj + clause)
    conj = "& "
  lines.append("-> false")
  #  \forall int v0; \forall int v1; (v1 >= 2 | -1 >= v1 | 0 >= v0 | IsOdd(1 + v0, v1))

  lines.append("}")

  tmp_file = "_tmp.pri"
  with open(tmp_file, "w") as princess_file:
    princess_file.write("\n".join(lines))

  output = run_cmd([princess_command, "-timeout=5000", "-clausifier=simple", tmp_file])
  
  if output and 'output' in output:
    for line in output['output'].splitlines():
      if line.rstrip() == "INVALID":
        log.debug("Task is UNSAT (which is good)")
        return True
      elif line.rstrip() == "VALID":
        log.debug("Task is SAT")
        return False
      elif line.startswith("ERROR:"):
        log.debug("Check failed: {}".format(line))
        return False
      elif line.startswith("CANCELLED/TIMEOUT"):
        log.debug("Timeout")
        return True
  #  return True
  log.debug("Check failed: \n{}".format(output['output']))
  return False

def parse_output(output_string):
  problem = dict()
  current_clause_key = ""
  buffer = ""

  for line in output_string.splitlines():
    if "sat" == line :
      problem["solved"] = True
      return problem
    elif line == "unsat":
      problem["solved"] = True
      return problem

    if line=="**All Clauses":
      buffer=""
      current_clause_key = clauses_key
      problem[current_clause_key] = list()
    elif line=="---": 
      if current_clause_key!="":
        if buffer.rstrip() != "true":
          problem[current_clause_key].append(buffer)
      buffer = ""
    elif line=="**End Clauses":       
      buffer = ""
    elif line=="**Instantiated Clauses with Violating Predicates:": 
      buffer=""
      current_clause_key = instantiated_clause_key
      problem[instantiated_clause_key] = list()
    elif line=="**VIOLATED CLAUSES:": 
      buffer=""
      current_clause_key = violated_clause_key
      problem[current_clause_key] = list()
    elif line=="**Other Clauses with Violating Predicates:": 
      buffer=""
      current_clause_key = ""
      #problem[violated_clause_key] = list()
    elif line=="End violated": 
      #problem[violated_clause_key].append(buffer)
      buffer = ""
    elif line=="**Violating Predicates:": 
      buffer=""
      problem[predicate_key] = ""
    elif line=="**End Predicates":
      problem[predicate_key] = buffer
      buffer = ""
    elif line=="psat": 
      buffer=""
    else:
      if len(buffer)>0:
        buffer+="\n"
      buffer+=line
  return problem

def parse_predicate_keys(pred_keys):
  parsed_keys = list()
  i=0
  lastKey = ""
  for line in pred_keys.splitlines():    
    parsed_key = dict()
    if i%2 == 0:
      lastKey = line
    else:
      parsed_key = dict()
      parsed_key["name"] = lastKey[:lastKey.index('(')]
      param_string = lastKey[lastKey.index('(')+1:lastKey.index(')')]      
      parsed_key["args"] = [x.strip() for x in param_string.split(',')]      
      parsed_key["assignment"] = line
      parsed_keys.append(parsed_key)
    i+=1
  return parsed_keys



def create_tasks(eldarica_output, problem):
  tasks = list()
  relevant_clauses = list()
  #first add all violated clauses

  #TODO temporarily disabled
  # relevant_clauses += eldarica_output[violated_clause_key]
  
  #then add each power set of the remaining instantiated clauses
  counter = 0

  
  subset = eldarica_output[instantiated_clause_key]
  
  #for subset in powerset(eldarica_output[instantiated_clause_key]):
  # if len(subset)==0:
  #   continue
  # if counter>MAX_TASKS_PER_PROBLEM:
  #   break    
  task = dict()
  task[problem_id_key] = problem[problem_id_key]
  task[predicate_key] = problem[predicate_key]
  task[clauses_key] = list()
  task[clauses_key] += relevant_clauses
  for clause in subset:
    task[clauses_key].append(clause)
  tid = h.sha224(str(task).encode('utf-8')).hexdigest()
  task[task_id_key] = str(tid)      
  # compute the hash before setting the random name
  log.info("Checking satisfiability of task.")
  if check_solvable(task) == True:
    counter += 1
    tasks.append(task)
  else:
    #print "Unsat. Dropping task"
    pass

  if counter == 0 :
    log.info("Could not generate new tasks %s", str(json.dumps(eldarica_output, indent=2)))
  return tasks


def create_problem_hash(eldarica_output):
  hash_string = "\n".join(eldarica_output[instantiated_clause_key])
  hash_string += eldarica_output[predicate_key]
  return h.sha224(hash_string.encode('utf-8')).hexdigest()

def check_smt_file(smt_file, out_dir, timeout=5, hint_file=None, problem=None, generate=True):
  global TOTAL_PROBLEM, TOTAL_TASK
  cmd = [eldarica_command, smt_file, "-rt:{}".format(timeout), "-ssol"]
  if hint_file:
    cmd+=["-hints:{}".format(hint_file)]
  log.info("Calling Eldarica: %s", " ".join(cmd))
  stats = run_cmd(cmd)
  eldarica_output = None
  if stats and not stats['timed_out']:
    eldarica_output = parse_output(stats["output"])
  generated_tasks = 0
  try:
    log.info("Eldarica says ====\n%s\n=====\n", stats["output"])
    if eldarica_output: 

      if "solved" in eldarica_output:
        log.info("Problem solved: {}", eldarica_output)
        if problem !=None:
          return problem[problem_id_key], True, 0
        else:
          return "0", eldarica_output["solved"], 0

      # create a new problem if needed.
      pid = create_problem_hash(eldarica_output)
      unique_problem_name = os.path.join(out_dir,"problem_{}.json".format(pid))

      smt_file_copy=None
      # if we check a known problem, check if
      # anything changed.
      if problem and problem[problem_id_key]!=pid:
        #create a new problem but use the old smt file.
        smt_file_copy = problem["smt_file"]
        problem = None

      if os.path.isfile(unique_problem_name):
        with open(unique_problem_name, "r") as data_file:
          log.warning("Problem already created: %s", str(unique_problem_name))
          problem = json.load(data_file)

      if problem==None:
        problem = dict()
        problem[problem_id_key] = str(pid)
        if "solved" in eldarica_output:
          log.info("solved in Eldarica's output") 
          return problem[problem_id_key], True, 0 
        problem[clauses_key] = eldarica_output[clauses_key]
        problem[instantiated_clause_key] = eldarica_output[instantiated_clause_key]
        problem[predicate_key] = parse_predicate_keys(eldarica_output[predicate_key])

        if smt_file_copy == None:
          smt_file_dir = os.path.join(os.path.dirname(out_dir), SMT_DIR_SUFFIX)
          if not os.path.exists(smt_file_dir):
            os.makedirs(smt_file_dir)
          smt_file_copy = os.path.join(smt_file_dir, "smt_{}.smt2".format(str(pid)))
          copyfile(smt_file, smt_file_copy)

        problem["smt_file"] = smt_file_copy
        problem_file = "problem_{}.json".format(pid)
        with open(os.path.join(out_dir, problem_file), "w") as jo:
          jo.write(json.dumps(problem, indent=2))
          TOTAL_PROBLEM+=1
      if "solved" in eldarica_output:
        log.info("solved in Eldarica's output") 
        return problem[problem_id_key], True, 0
      
      log.info("Creating tasks.")
      for task in create_tasks(eldarica_output, problem):
        task_file_name = os.path.join(out_dir, "task_{0}.json".format(task[task_id_key]))
        if os.path.isfile(task_file_name):
          log.info("Task already in DB: %s", str(task_file_name))
          continue
        task["smt_file"] = problem["smt_file"]
        task["text_name"] = haikunator.haikunate(token_length=0, delimiter=' ')
    
        if generate:        
          log.info("Generating %s", str(task_file_name))
          with open(task_file_name, "w") as jo:
            jo.write(json.dumps(task, indent=2))
            TOTAL_TASK+=1
            generated_tasks+=1
      log.info("Success. Generated %s tasks", str(generated_tasks))
  except Exception as e:
    log.error("Failed. %s", str(e))
    traceback.print_exc(file=sys.stdout)

  if problem:
    return problem[problem_id_key], False, generated_tasks
  return "0", False, 0

def generate_problem_file(smt_file_list, out_dir, timeout=2, hint_file=None):
  global TOTAL_PROBLEM, TOTAL_TASK, TOTAL_NO_TASK
  
  if not os.path.exists(out_dir):
    os.makedirs(out_dir)

  for smt_file in smt_file_list:
    log.info("Processing %s", str(smt_file))
    uid,solved,gentasks = check_smt_file(smt_file, out_dir, timeout, None, None)
    if gentasks==0 and solved == False:
      TOTAL_NO_TASK+=1

      #print stats
      #raise e
    


def get_file_hash(file_name):
  file_data = ""
  with open(file_name, "r") as f:
    file_data = f.read()
  return h.sha224(file_data).hexdigest()



### Only Utility stuff below this point ###
def powerset(iterable):
  "powerset([1,2,3]) --> () (1,) (2,) (3,) (1,2) (1,3) (2,3) (1,2,3)"
  s = list(iterable)
  return itertools.chain.from_iterable(itertools.combinations(s, r) for r in range(len(s)+1))

if __name__ == "__main__":
  if len(sys.argv)<3:
    print("Requires smt file dir and out dir")
    sys.exit()
  if not os.path.isdir(sys.argv[1]):
    print("SMT dir not a directory: {}".format(sys.argv[1]))
    sys.exit()
  smt_files = []
  for (dirpath, _, filenames) in walk(sys.argv[1]):
    for fn in filenames:
      if ".smt2" in fn:
        TOTAL_SMT+=1
        smt_files.append(os.path.join(dirpath, fn))
    break
  generate_problem_file(smt_files, sys.argv[2])
  print("Files {}, Problems {}, Tasks {}".format(TOTAL_SMT, TOTAL_PROBLEM, TOTAL_TASK))
  print("Problems without tasks {}".format(TOTAL_NO_TASK))
  

