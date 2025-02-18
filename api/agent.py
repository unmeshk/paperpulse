# Contains all of the Open AI calls
import openai
from openai import OpenAI
import os
import logging

from api.settings import SUMMARY_PROMPT, COMBINE_PROMPT

openai.api_key = os.getenv("OPENAI_API_KEY")

logger = logging.getLogger(__name__)



class Agent:
    def __init__(self, openai_api_key):
        openai.api_key = openai_api_key

    def _combine_paper_info(self, paper):
        """
        Combines the title, authors, and summary into a single string

        Args:
        paper: the dict containing details of the paper
        """
        return f"**Title:** {paper['title']}\n**Authors:** {', '.join(paper['authors'])}\n**Summary:** {paper['summary']}\n"

    def _batch_papers(self, papers, max_length, prompt_template):
        """
        Splits papers into batches that when combined stay under max_length.
        
        Args:
            papers: List of paper dictionaries
            max_length: Maximum allowed length for combined papers
            prompt_template: Template text that will be added to each batch
            
        Returns:
            List of paper batches, where each batch is a list of paper dictionaries
        """
        batches = []
        current_batch = []
        current_length = len(prompt_template)
        
        for paper in papers:
            paper_info = self._combine_paper_info(paper)
            paper_length = len(paper_info)
            
            # If adding this paper would exceed max_length, start a new batch
            if current_length + paper_length > max_length and current_batch:
                batches.append(current_batch)
                current_batch = []
                current_length = len(prompt_template)
                
            current_batch.append(paper)
            current_length += paper_length
        
        # Add the last batch if it's not empty
        if current_batch:
            batches.append(current_batch)
            
        logger.info(f"Split {len(papers)} papers into {len(batches)} batches")
        return batches

    def _call_llm(self, prompt, max_tokens = 5000):
        """
        Helper function to make LLM API calls.
        
        Args:
            prompt: The prompt to send to the LLM
            max_tokens: Maximum tokens for the response
            
        Returns:
            The LLM's response text
        
        Raises:
            Exception: If the API call fails
        """
        try:
            messages = [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ]
            
            response = openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.1,
                top_p=0.9
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"LLM API call failed: {str(e)}")
            raise

    def identify_important_papers(self, papers):
        """
        Processes papers in batches and generates a combined summary using multiple LLM calls.
        
        Args:
            papers: List of dictionaries containing paper information
            
        Returns:
            A comprehensive summary of all papers
            
        Raises:
            ValueError: If papers list is empty
        """
        if not papers:
            raise ValueError("No papers provided to summarize")
            
        # Constants
        MAX_LENGTH = 122000 * 4  # max len = max tokens * 4 since on average a word is ~4 tokens
        
        # Get paper batches
        batches = self._batch_papers(papers, MAX_LENGTH, SUMMARY_PROMPT)
        intermediate_summaries = []
        
        # Process each batch
        for i, batch in enumerate(batches, 1):
            logger.info(f"Processing batch {i} of {len(batches)}")
            
            # Combine papers in this batch
            batch_info = "\n".join(self._combine_paper_info(p) for p in batch)
            prompt = SUMMARY_PROMPT + batch_info
            
            try:
                # Get summary for this batch
                batch_summary = self._call_llm(prompt)
                intermediate_summaries.append(batch_summary)
                logger.info(f"Successfully processed batch {i}")
                
            except Exception as e:
                logger.error(f"Failed to process batch {i}: {str(e)}")
                continue
        
        # If we have multiple summaries, combine them
        if len(intermediate_summaries) > 1:
            combine_prompt = COMBINE_PROMPT + "\n\n".join(intermediate_summaries)
            
            try:
                final_summary = self._call_llm(combine_prompt)
            except Exception as e:
                logger.error(f"Failed to combine summaries: {str(e)}")
                # Fall back to concatenation if combination fails
                final_summary = "\n\n".join(intermediate_summaries)
        else:
            final_summary = intermediate_summaries[0] if intermediate_summaries else ""
        
        return final_summary

    def summarize_paper(self, pdf_file):
        """
        Summarizing a paper is a 5 step process that uses openai's beta client / message thread 
        approach which allows a pdf file to be uploaded. OpenAI creates a vector store that 
        then answers queries using a RAG approach to answer questions.
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
        messages = self._create_and_run_thread(
            client,
            "You are an expert ML researcher and engineer. Provide a summary of under 500 words of this paper for an audience of ML research scientists.",
            assistant.id
        )
        summaries.append(messages[0].content[0].text.value)

        # then the related work
        print('Generating related work summary...')
        messages = self._create_and_run_thread(
            client,
            "You are an expert ML researcher and engineer. Provide a summary of the related work that is referenced in this paper. Make the summary suitable for an audience of ML research scientists.",
            assistant.id
        )
        summaries.append(messages[0].content[0].text.value)

        # the approach
        print('Generating summary of approach...')
        messages = self._create_and_run_thread(
            client,
            "You are an expert ML researcher and engineer. Provide a summary of the approach that the authors present in the paper. Make the summary suitable for an audience of ML research scientists.",
            assistant.id
        )
        summaries.append(messages[0].content[0].text.value)

        # the results
        print('Generating summary of results...')
        messages = self._create_and_run_thread(
            client,
            "You are an expert ML researcher and engineer. Provide a summary of the results in the paper. Make the summary suitable for an audience of ML research scientists.",
            assistant.id
        )
        summaries.append(messages[0].content[0].text.value)

        # and finally the conclusion
        print('Generating summary of discussion and future work...')
        messages = self._create_and_run_thread(
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
        narrative = self._combine_paper_summaries(summaries)

        return narrative
        print(f'Deleted vector stores: {ids}')
        


    def _create_and_run_thread(self, client, content, assistant_id):
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

    def _combine_paper_summaries(self, summaries):
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