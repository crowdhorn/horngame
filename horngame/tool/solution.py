import sys, os, traceback, itertools, tempfile
from os import walk
import json
import subprocess32 as subprocess

from pyparsing import *

from common import *
import problems

class InconsistentPredicateException(Exception):
    pass

"""
check_solution receives json of that form 
{
  "task_id" : 8xyz_uuid,
  "problem_id" : 15asfba_uuid,
  "preds": [
    {
      "assignment": "v1 == v0 % 2", 
      "args": [
        "v0", 
        "v1"
      ], 
      "name": "IsOdd"
    }
  ]
}
in the form of a dictionary and the path where all the 
task and problem files are.

First it checks if any of the assignments is inconsistent. If so,
it throws an InconsistentPredicateException.

Then it checks if the clauses are valid under the assignment and
returns a list of integers with one entry per clause where 1 means
the clause is valid, and 0 means it is not or couldn't be solved. 
"""
def check_solution(solution, sol_dir):
  task = load_task(sol_dir, solution[task_id_key])
  # check for each clause individually if the assignment makes it valid
  valid_clauses = []

  create_princess_tautology_check(solution)

  for clause in task[clauses_key]:
    output = dict()   
    with tempfile.NamedTemporaryFile(mode='w', suffix='.pri') as pri_file:
      create_princess_file(sol_dir, solution, [clause], pri_file)
      pri_file.flush()
      output = run_cmd([princess_command, "-timeout=1000", "-clausifier=simple", pri_file.name])
    # log.info("Output of princess: %s", str(output))
    valid_clauses += [0]
    if parse_princess_output(output) == True:
      valid_clauses[-1] = 1

  # print("{}/{} clauses valid".format(valid_clauses, len(task[clauses_key])))
  return valid_clauses

# =========== helper methods for check_solution =============

def parse_princess_output(output):
  if output and 'output' in output:
    for line in output['output'].splitlines():
      if line.rstrip() == "VALID":
        return True
      elif line.rstrip().startswith("ERROR"):
        raise SyntaxError(line)
  return False

def create_princess_tautology_check(solution):
  res = []
  for pred in solution[predicate_key]:    
    lines = list()
    lines.append("\\predicates {")

    #conj with &
    type_sig=""
    comma = ""
    for arg in pred["args"]:
      type_sig+=comma
      comma = ", "
      type_sig+="int "+arg
    lines.append("  {}({});".format(pred["name"], type_sig))
    lines.append("}")


    lines.append("\\functions {")
    #conj with &
    type_sig="int "
    comma = ""
    for arg in pred["args"]:
      type_sig+=comma
      comma = ", "
      type_sig+=arg
    lines.append("{};".format(type_sig))
    lines.append("}")


    lines.append("\\problem {")  
    lines.append(pred["assignment"])
    lines.append("-> false ")    

    lines.append("}")
    output = None
    with tempfile.NamedTemporaryFile(mode='w', suffix='.pri') as pri_file:
      pri_file.write("\n".join(lines))
      pri_file.flush()
      output = run_cmd([princess_command, "-timeout=1000", "-clausifier=simple", pri_file.name])
    if parse_princess_output(output):
      raise InconsistentPredicateException(pred["name"])

 

"""
creates a pri file to check with princess if the user provided 
predicates make all clauses valid.
"""
def create_princess_file(sol_dir, solution, list_of_clauses, out_file):
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
      type_sig+="int "+arg
    lines.append("  {}({}) {{ {} }};".format(pred["name"], type_sig, pred["assignment"]))
  lines.append("}")

  lines.append("\\problem {")  
  conj = ""
  for clause in list_of_clauses:
    lines.append(conj + clause)
    conj = "& "
  #  \forall int v0; \forall int v1; (v1 >= 2 | -1 >= v1 | 0 >= v0 | IsOdd(1 + v0, v1))

  lines.append("}")
  text = "\n".join(lines)
  #print text
  out_file.write(text)
  

#======== check solution against SMT file ========

"""
  Takes a user-provided solution and re-runs the Horn solver
  with this solution as a hint. 
  It call the same method problems.check_smt_file that we use
  to generate problems.
"""
def check_solution_against_smt_file(sol, problem_dir, base_dir, generate=True):
  probl = load_problem(problem_dir, sol[problem_id_key])
  hint_file_name = create_tuple_file_from_solution(sol)
  smt_file_name = os.path.join(base_dir, probl["smt_file"])
  return problems.check_smt_file(smt_file_name, problem_dir, timeout=10, hint_file=hint_file_name, problem=probl, generate=generate)

"""
ONLY UTILITY METHODS BELOW THIS POINT
"""

# returns the name of the tuple file.
def create_tuple_file_from_solution(sol): 
  cegar_list = []
  for pred in sol[predicate_key]:
    pri_string = "\\functions {\n"
    pri_string += "int "
    comma = ""
    for arg in pred["args"]:
      pri_string+=comma + arg
      comma = ", "
    pri_string +=";\n}\n"
    pri_string += "\\problem { !(\n" + pred["assignment"] +"\n)}\n"

    with tempfile.NamedTemporaryFile(mode='w', suffix='.pri') as pri_file:
      pri_file.write(pri_string)   
      pri_file.flush()

      smt_file = tempfile.NamedTemporaryFile(delete=False, suffix=".smt2")
      output = run_cmd([princess_command, "-timeout=0", pri_file.name, "-printSMT={}".format(smt_file.name)])
      
      cegar_string = "(initial-predicates "
      cegar_string += pred["name"]+"("
      for arg in pred["args"]:
        cegar_string +="(" + arg +" Int)"
      cegar_string += ")"
      cegar_string += get_assertion_line_from_file(smt_file.name)
      cegar_string += ")"
      cegar_list += [cegar_string]
      os.unlink(smt_file.name)

  print ("\n".join(cegar_list))
  tpl_file = tempfile.NamedTemporaryFile(delete=False, suffix=".tpl")
  tpl_file.write("\n".join(cegar_list))
  tpl_file.close()
  return tpl_file.name


## only boiler plate below this point ##

def get_assertion_line_from_file(smt_file_name):
  with open(smt_file_name, "r") as f:
    data = "({})".format(f.read())
  for outer in nestedExpr(opener='(', closer=')').parseString(data):
    for el in outer:
      if el[0]=="assert":
        return print_ptree(el[1])

def print_ptree(ptree):
  if isinstance(ptree, basestring):
    return ptree
  ret = "("
  space = ""
  for el in ptree:
    ret += space + print_ptree(el)
    space = " "
  ret+=")"
  return ret


def make_test_solution():
  solution = dict()
  solution[task_id_key] = "97e5ee774a4c66c579276d0644a3d6b5172afd9b069c4809f0e4041b"
  solution[problem_id_key] = "c4178476de99aae26ccf3ffcd85dfcffcfbe5cb0610c29b4a046ed80"
  solution[predicate_key] = list()
  pred = dict()
  pred["assignment"] = "3>v0"
  pred["args"] = ["v0", "v1"]
  pred["name"] = "IsOdd"
  solution["preds"].append(pred)

  return solution


if __name__ == "__main__":
  if len(sys.argv)<2:
    print("Requires json file dir")
    sys.exit()
  if not os.path.isdir(sys.argv[1]):
    print("Json dir not a directory: {}".format(sys.argv[1]))
    sys.exit()
  print(check_solution(make_test_solution(), sys.argv[1]))
  