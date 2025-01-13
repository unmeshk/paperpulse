# Contains all of the Open AI calls
import openai
from openai import OpenAI
import os

openai.api_key = os.getenv("OPENAI_API_KEY")

def summarize_paper(pdf_file):
    """
    Summarizing a paper is a 5 step process that uses openai's beta client / message thread 
    approach which allows a pdf file to be uploaded. OpenAI creates a vector store that is 
    then queries using a RAG approach to answer questions.
    Known Issues:
       1. RAG approach has a max of 4000 tokens. This means asking broad questions is not possible
       Workaround is to break up the summarization into the following sets of questions.
            a. Summary of the paper (uses the abstract)
            b. Related work
            c. Approach
            d. Results
            e. Discussion, future work, and any relevant core papers
        2. Images aren't supported currently so it won't be able to read and process tables, charts, images
        or return information in that form.

    Args:
        pdf_file (str): file path to the downloaded pdf file

    Returns:
        summary (str): A summary that combines the answers to the above questions.
    """

    client = OpenAI()

    assistant = client.beta.assistants.create(
        name="ML Research Assistant",
        instructions="You are an expert ML researcher and engineer.",
        model="gpt-4o-mini",
        tools=[{"type": "file_search"}],
    )

    # Create a vector store caled "Financial Statements"
    vector_store = client.beta.vector_stores.create(name=pdf_file)

    # Ready the files for upload to OpenAI
    file_paths = [pdf_file]
    file_streams = [open(path, "rb") for path in file_paths]

    # Use the upload and poll SDK helper to upload the files, add them to the vector store,
    # and poll the status of the file batch for completion.
    file_batch = client.beta.vector_stores.file_batches.upload_and_poll(
        vector_store_id=vector_store.id, files=file_streams
    )

    assistant = client.beta.assistants.update(
        assistant_id=assistant.id,
        tool_resources={"file_search": {"vector_store_ids": [vector_store.id]}},
    )

    # first the summary
    print('Generating high-level summary...')
    summaries = []
    messages = create_and_run_thread(
        client,
        "You are an expert ML researcher and engineer. Provide a summary of under 500 words of this paper for an audience of ML research scientists.",
        assistant.id
    )
    summaries.append(messages[0].content[0].text.value)

    # then the related work
    print('Generating related work summary...')
    messages = create_and_run_thread(
        client,
        "You are an expert ML researcher and engineer. Provide a summary of the related work that is referenced in this paper. Make the summary suitable for an audience of ML research scientists.",
        assistant.id
    )
    summaries.append(messages[0].content[0].text.value)

    # the approach
    print('Generating summary of approach...')
    messages = create_and_run_thread(
        client,
        "You are an expert ML researcher and engineer. Provide a summary of the approach that the authors present in the paper. Make the summary suitable for an audience of ML research scientists.",
        assistant.id
    )
    summaries.append(messages[0].content[0].text.value)

    # the results
    print('Generating summary of results...')
    messages = create_and_run_thread(
        client,
        "You are an expert ML researcher and engineer. Provide a summary of the results in the paper. Make the summary suitable for an audience of ML research scientists.",
        assistant.id
    )
    summaries.append(messages[0].content[0].text.value)

    # and finally the conclusion
    print('Generating summary of discussion and future work...')
    messages = create_and_run_thread(
        client,
        "You are an expert ML researcher and engineer. Provide a summary of any disucssion, conclusion, and future work sections in the paper. Make the summary suitable for an audience of ML research scientists.",
        assistant.id
    )
    summaries.append(messages[0].content[0].text.value)

    # try deleting the file and then list the vector stores again. 
    # client.files.delete(os.path.basename(pdf_file))
    ids = [store.id for store in openai.beta.vector_stores.list()]
    for id in ids:
        delid = client.beta.vector_stores.delete(id)

    # combine all of the text into a coherent narrative
    print('Generating full narrative ...')
    narrative = combine_paper_summaries(summaries)

    return narrative
    print(f'Deleted vector stores: {ids}')
    


def create_and_run_thread(client, content, assistant_id):
    """
    Creates and runs the message thread that queries OpenAI

    Args:
        client (object): OpenAI client
        content (str): the prompt
        assistant_id (str): id of the assistant used in the openai call

    Returns:
        message (object): the message returned from the openai call
    """

    # Create a thread
    thread = client.beta.threads.create(
        messages=[
            {
                "role": "user",
                "content": content,
            }
        ]
    )

    run = client.beta.threads.runs.create_and_poll(
        thread_id=thread.id,
        assistant_id=assistant_id)

    messages = list(client.beta.threads.messages.list(thread_id=thread.id, run_id=run.id))

    return messages

def combine_paper_summaries(summaries):
    """
    Combine the separate summaries of the paper into one coherent narrative

    Args:
        summaries (list): a list of the different summaries

    Returns:
        str: a summary that combines the different summaries
    """

    prompt = """ You are an accomplished AI and Machine Learning research scientist and educator. 
    You are also an expert English proof reader and summarizer who can explain concepts.
    Take all of the information below the heading SUMMARIES and convert that text into a coherent 
    narrative that's short, compact, and easy to read. 

    SUMMARIES

    """
    prompt = prompt + ''.join(summaries)

    # get summaries
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": prompt}
    ]

    # Call the OpenAI API
    response = openai.chat.completions.create(
        model="gpt-4o-mini", 
        messages=messages,
        max_tokens=5000, 
        temperature=0.1,
        top_p=0.9,  # Adjust as needed
    )

    # Extract the paper titles from the response
    return(response.choices[0].message.content)