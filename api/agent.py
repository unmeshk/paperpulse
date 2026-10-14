import logging

from api.model_budget import BudgetError, ModelBudget
from api.model_calls import create_client, generate_text
from api.settings import SUMMARY_PROMPT, COMBINE_PROMPT, budget_directory

logger = logging.getLogger(__name__)



class Agent:
    def __init__(self, gemini_api_key, budget=None, purpose="production"):
        self.client = create_client(gemini_api_key)
        self.budget = budget
        self.purpose = purpose
        self.stop_error = None

    def _combine_paper_info(self, paper):
        """
        Combines the title, authors, and summary into a single string

        Args:
        paper: the dict containing details of the paper
        """
        return f"**Title:** {paper['title']}\n**URL:** {paper['url']}\n**Authors:** {', '.join(paper['authors'])}\n**Summary:** {paper['summary']}\n"

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

    def _call_llm(self, prompt, max_tokens=5000):
        if self.stop_error is not None:
            raise self.stop_error
        if self.budget is not None:
            return generate_text(self.client, self.budget, prompt, max_tokens, purpose=self.purpose)
        # Direct callers (including future evaluation tooling) use the same
        # configured durable ledger; no automatic or in-memory allowance.
        try:
            directory = budget_directory()
        except ValueError as err:
            raise BudgetError(str(err)) from err
        with ModelBudget(directory) as budget:
            return generate_text(self.client, budget, prompt, max_tokens, purpose=self.purpose)

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
                batch_summary = self._call_llm(prompt)
                intermediate_summaries.append(batch_summary)
                logger.info(f"Successfully processed batch {i}")
            except BudgetError as err:
                self.stop_error = err
                break
            except Exception as e:
                logger.error(f"Failed to process batch {i}: {str(e)}")
                continue

        
        # If we have multiple summaries, combine them
        if self.stop_error is not None:
            if not intermediate_summaries:
                raise self.stop_error
            # Preserve already completed summaries without another paid combine.
            final_summary = "\n\n".join(intermediate_summaries)
        elif len(intermediate_summaries) > 1:
            combine_prompt = COMBINE_PROMPT + "\n\n".join(intermediate_summaries)
            
            try:
                final_summary = self._call_llm(combine_prompt)
            except BudgetError as err:
                self.stop_error = err
                final_summary = "\n\n".join(intermediate_summaries)
            except Exception as e:
                logger.error(f"Failed to combine summaries: {str(e)}")
                # Fall back to concatenation if combination fails
                final_summary = "\n\n".join(intermediate_summaries)
        else:
            final_summary = intermediate_summaries[0] if intermediate_summaries else ""
        
        return final_summary

    # TODO: remove summarize_paper, _create_and_run_thread, _combine_paper_summaries in a future commit
    # def summarize_paper(self, pdf_file):
    #     client = OpenAI()
    #     assistant = client.beta.assistants.create(
    #         name="ML Research Assistant",
    #         instructions="You are an expert ML researcher and engineer.",
    #         model="gpt-4o-mini",
    #         tools=[{"type": "file_search"}],
    #     )
    #     vector_store = client.beta.vector_stores.create(name=pdf_file)
    #     file_streams = [open(path, "rb") for path in [pdf_file]]
    #     client.beta.vector_stores.file_batches.upload_and_poll(
    #         vector_store_id=vector_store.id, files=file_streams
    #     )
    #     assistant = client.beta.assistants.update(
    #         assistant_id=assistant.id,
    #         tool_resources={"file_search": {"vector_store_ids": [vector_store.id]}},
    #     )
    #     summaries = []
    #     for prompt in [
    #         "Provide a summary of under 500 words of this paper for an audience of ML research scientists.",
    #         "Provide a summary of the related work that is referenced in this paper.",
    #         "Provide a summary of the approach that the authors present in the paper.",
    #         "Provide a summary of the results in the paper.",
    #         "Provide a summary of any discussion, conclusion, and future work sections in the paper.",
    #     ]:
    #         messages = self._create_and_run_thread(client, prompt, assistant.id)
    #         summaries.append(messages[0].content[0].text.value)
    #     ids = [store.id for store in openai.beta.vector_stores.list()]
    #     for id in ids:
    #         client.beta.vector_stores.delete(id)
    #     return self._combine_paper_summaries(summaries)

    # def _create_and_run_thread(self, client, content, assistant_id):
    #     thread = client.beta.threads.create(messages=[{"role": "user", "content": content}])
    #     run = client.beta.threads.runs.create_and_poll(thread_id=thread.id, assistant_id=assistant_id)
    #     return list(client.beta.threads.messages.list(thread_id=thread.id, run_id=run.id))

    # def _combine_paper_summaries(self, summaries):
    #     prompt = ("You are an ML research scientist. Convert the following summaries into a coherent "
    #               "narrative that's short, compact, and easy to read.\n\nSUMMARIES\n\n")
    #     return self._call_llm(prompt + ''.join(summaries))
