# AI use disclosure

**Tools used:** 
Codex

**What I used them for:**
I used Codex to get started with an initial implementation of the code for collecting source-tagged text, applying topic labels, calculating daily sentiment measures, retrieving event-contract history, and constructing market-adjusted equity returns. I also used it to troubleshoot API, data parsing, and notebook execution errors.

**What I wrote myself:**
I implemented and set up the Python code in the notebook for outputting the required tables and figures. I also reviewed the code and associated outputs that Codex wrote in the notebook to ensure that assignment requirements were met, and I wrote out the interpretations of the tables and figures in the report. 

**Anything the model got wrong that I had to correct:**

The initial implementation had collected data with mixed timestamp formats and ths initially caused valid non-GDELT records to be dropped after filtering, so the data parsing logic had to be corrected. There were also various libaries assumed to be imported that were not that had to be added. In addition, there were some other public social sources that the model thought had available data (i.e. Bluesky) but in reality did not have data available (return HTTP 403 errors) so those implementations could not be included.  
