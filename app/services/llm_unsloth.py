import torch
from unsloth import FastLanguageModel
from peft import PeftModel

alpaca_prompt = """Below is an instruction that describes a task, paired with an input that provides further context. Write a response that appropriately completes the request.

### Instruction:
{}

### Input:
{}

### Response:
{}"""

class UnslothEngine:
    def __init__(self, base_model_name: str, lora_path: str, max_seq_length=2048):
        self.base_model_name = base_model_name
        self.lora_path = lora_path
        self.max_seq_length = max_seq_length

        self.model = None
        self.tokenizer = None

    def load(self):
        self.model, self.tokenizer = FastLanguageModel.from_pretrained(
            model_name=self.base_model_name,
            max_seq_length=self.max_seq_length,
            dtype=None,
            load_in_4bit=True,
        )

        self.model = PeftModel.from_pretrained(self.model, self.lora_path)

        FastLanguageModel.for_inference(self.model)
        self.model.eval()

    @torch.inference_mode()
    def generate(self, instruction: str, input_text: str = "", max_new_tokens=256, temperature=0.7, top_p=0.9) -> str:
        prompt = alpaca_prompt.format(instruction, input_text, "")
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)

        outputs = self.model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=True,
            temperature=temperature,
            top_p=top_p,
            pad_token_id=self.tokenizer.eos_token_id,
            eos_token_id=self.tokenizer.eos_token_id,
        )

        decoded = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        if "### Response:" in decoded:
            decoded = decoded.split("### Response:")[-1].strip()
        return decoded.strip()
