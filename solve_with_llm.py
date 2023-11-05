import sys, os, boto3, logging, traceback
import json

from langchain.memory import ConversationBufferMemory
from langchain.prompts import PromptTemplate
from langchain.llms.bedrock import Bedrock
from langchain.chains import ConversationChain


os.environ['ELDARICA_PATH'] = os.path.join(os.getcwd(), "eldarica")

sys.path.append("./horngame/tool")
import problems
import common
import solution

PROBLEM_DIR = os.path.join(os.getcwd(), "horngame/static", common.PROBLEM_DIR_SUFFIX)



def collect_tasks(dir=PROBLEM_DIR):
    for root, dirs, files in os.walk(dir):
        for f in files:
            if f.startswith("task_") and f.endswith(".json"):
                yield os.path.join(root, f)


def check_solution(task, problem_dir=PROBLEM_DIR):
    try:
        valid_clauses = solution.check_solution(task, problem_dir)
        print('check_solution: %s' % str(valid_clauses))
        return valid_clauses
    except SyntaxError as texterror:
        print(texterror)
        return [0]
    except solution.InconsistentPredicateException as tauterror:
        errortext = ("Dude, don't use inconsistent formulas for {}!".format(tauterror))
        print(errortext)
        return [0]

def load_task(task_path):
    with open(task_path) as f:
        task = json.load(f)
    return task

def construct_query_for_task(task, results):

    prompt = """
We are trying to solve a system of constraint Horn clauses by finding appropriate
assignments for all predicates under which all individual clauses are valid.
Given the numbered list of constraint Horn clauses:
"""
    i = 0
    for clause in task["clauses"]:
        i += 1
        prompt += " {0})\t{1}\n".format(i, clause)

    prompt += " and the predicate assignments:\n"
    
    for pred in task["preds"]:
        pred_name = pred["name"]
        pred_with_args  = "{}({})".format(pred_name, ", ".join(pred["args"]))
        pred_assignment = pred['assignment']

        prompt += " {0} = {1}\n".format(pred_with_args, pred_assignment)
    
    valid_indices = [i+1 for i, x in enumerate(results) if x == 1]
    prompt += "We know that the clauses with numbers {} are valid. Improve these assignments such that all clauses become valid.".format(", ".join(map(str, valid_indices)))

    prompt+= "Return the answer in json format that maps each predicate to a new assignment."

    return prompt

def construct_example_answer(task):
    assignments = dict()
    for pred in task["preds"]:
        pred_name = pred["name"]
        pred_with_args  = "{}({})".format(pred_name, ", ".join(pred["args"]))
        pred_assignment = pred['assignment']

        assignments[pred_with_args] = pred_assignment
    return json.dumps(assignments, indent=2)


def create_context_with_examples(example_dir="example_prompts"):
    context = ConversationBufferMemory()
    context.human_prefix = "Human:"
    context.ai_prefix = "Assistant:"
    i = 1
    while os.path.exists(f"example_prompts/{i:02d}_task.json"):
        task_file = f"example_prompts/{i:02d}_task.json"
        task = load_task(task_file)
        res = check_solution(task)
        task_success = (res == [1]*len(res))
        if (res == [0]*len(res)):
            print("ERROR: Task is invalid. At least some clauses need to be valid under given assingment.")
            continue

        solution_file = f"example_prompts/{i:02d}_solution.json"
        solution_task = load_task(solution_file)
        res2 = check_solution(solution_task)
        solution_success = (res2 == [1]*len(res2))

        if not task_success and solution_success:
            question = construct_query_for_task(task, res)
            context.chat_memory.add_user_message(question)
            answer = construct_example_answer(solution_task)
            context.chat_memory.add_ai_message(answer)
        else:
            print("ERROR: unexpected result in context ", task_file)
        i+=1
    return context


def check_task_with_llm(conversation, task, problem_dir=PROBLEM_DIR):
    res = check_solution(task, problem_dir)
    if res == [1]*len(res):
        return res
    llm_query = construct_query_for_task(task, res)
    llm_response = ""
    try:
        llm_response = conversation.predict(input=llm_query)            
        first_index = llm_response.find('{')
        last_index = llm_response.rfind('}')
        new_assignment = json.loads(llm_response[first_index:last_index+1])
        print("New Assignment: ", new_assignment)
        abort = False
        while not abort:
            new_task = task
            for key in new_assignment:
                simple_key = key.split("(")[0]
                for pred in new_task["preds"]:
                    if pred["name"] is [simple_key]:
                        # TODO also check if the args match
                        pred["assignment"] = new_assignment[key]
            res = check_solution(task, problem_dir)
            if res == [1]*len(res):
                print("SUCCESS: ", res)
                return res
            print("TODO: now we need to refine because the answer is ", res)
            return res
    except json.decoder.JSONDecodeError as e:
        # Our logic to parse the LLM response failed.
        traceback.print_exc()
        return []
    except Exception as e:
        print("ERROR parsing ", llm_response)
        traceback.print_exc()
        return None
            
    return None


## Setup the LLM via Bedrock
context = create_context_with_examples()
PARAMS = {
    "max_tokens_to_sample": 8192,
    "temperature": 0.5,
    "top_k": 250,
    "top_p": 1,
    "stop_sequences": ["\n\nHuman"],
    }

bedrock_runtime = boto3.client(
    service_name='bedrock-runtime', 
    region_name='us-west-2'
)
claude_llm = Bedrock(model_id="anthropic.claude-v2",
                     model_kwargs=PARAMS,
                     client=bedrock_runtime, verbose=False)
conversation = ConversationChain(
     llm=claude_llm, verbose=False, memory=context
)

logging.basicConfig(level=logging.INFO)
boto3.set_stream_logger('', logging.ERROR)

tasks = list(collect_tasks())
print("################ Starting to solve {} tasks ###########".format(len(tasks)))

for task_file in tasks:
    task = load_task(task_file)
    print("Processing ", task['task_id'])
    res = check_task_with_llm(conversation, task)
    if not res:
        break

# first_task = load_task(tasks[0])
# print(first_task)

# print(check_solution(first_task))

# 7172349fe5542f427eea47956e75e00ad1440baca9508ed2b09f0804
