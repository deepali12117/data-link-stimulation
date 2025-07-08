import tkinter as tk
from tkinter import scrolledtext, messagebox
import random
import time
import threading

# --- Helper Functions for Data Link Layer Simulation ---

def generate_crc(data_bits, polynomial_bits):
    """
    Generates a Cyclic Redundancy Check (CRC) checksum for given data.
    This is a simplified CRC calculation for demonstration purposes.
    """
    data = [int(b) for b in data_bits]
    polynomial = [int(b) for b in polynomial_bits]
    n = len(polynomial)

    temp_data = list(data) + [0] * (n - 1)

    for i in range(len(data)):
        if temp_data[i] == 1:
            for j in range(n):
                temp_data[i + j] = temp_data[i + j] ^ polynomial[j]

    crc = "".join(str(b) for b in temp_data[len(data):])
    return crc

def check_crc(received_data_with_crc, polynomial_bits):
    """
    Checks the CRC of received data.
    Returns True if no error detected, False otherwise.
    """
    received_bits = [int(b) for b in received_data_with_crc]
    polynomial = [int(b) for b in polynomial_bits]
    n = len(polynomial)

    temp_received = list(received_bits)

    for i in range(len(received_bits) - n + 1):
        if temp_received[i] == 1:
            for j in range(n):
                temp_received[i + j] = temp_received[i + j] ^ polynomial[j]

    remainder = "".join(str(b) for b in temp_received[len(received_bits) - n + 1:])
    return int(remainder) == 0

# --- Data Link Layer Components ---

class DataLinkLayerNode:
    """
    Represents a node (Sender or Receiver) in the Data Link Layer.
    """
    def __init__(self, name, gui_logger, polynomial="1011"):
        self.name = name
        self.polynomial = polynomial
        self.send_buffer = []
        self.next_frame_to_send = 0
        self.expected_frame_ack = 0
        self.window_size = 3
        self.received_frames = {}
        self.next_frame_to_deliver = 0
        self.gui_logger = gui_logger # Reference to the GUI's log area

    def log(self, message):
        """Logs messages to the GUI's text area."""
        self.gui_logger.config(state=tk.NORMAL) # Enable writing
        self.gui_logger.insert(tk.END, f"[{self.name}] {message}\n")
        self.gui_logger.see(tk.END) # Auto-scroll to the end
        self.gui_logger.config(state=tk.DISABLED) # Disable writing

    def frame_data(self, data, sequence_number):
        """
        Performs framing: adds sequence number and CRC to the data.
        Frame format: [Sequence_Number (2 bits)] + [Data] + [CRC (3 bits)]
        """
        seq_num_binary = bin(sequence_number % 4)[2:].zfill(2)
        data_bits = ''.join(format(ord(char), '08b') for char in data)
        frame_payload = seq_num_binary + data_bits
        crc = generate_crc(frame_payload, self.polynomial)
        frame = frame_payload + crc
        self.log(f"Framing data '{data}' (Seq:{sequence_number}) -> Payload: '{frame_payload}' -> CRC: '{crc}' -> Full Frame: '{frame}'")
        return frame

    def unframe_data(self, frame):
        """
        Extracts data and checks CRC from a received frame.
        Returns (sequence_number, data, is_corrupted)
        """
        if len(frame) < len(self.polynomial) - 1 + 2:
            self.log(f"Received frame too short: {frame}")
            return None, None, True

        is_corrupted = not check_crc(frame, self.polynomial)
        if is_corrupted:
            self.log(f"CRC Check Failed for frame: {frame} -> Frame is CORRUPTED!")
            return None, None, True

        seq_num_binary = frame[0:2]
        data_bits = frame[2:-len(self.polynomial)+1]
        
        sequence_number = int(seq_num_binary, 2)
        data = ""
        for i in range(0, len(data_bits), 8):
            byte = data_bits[i:i+8]
            if byte:
                data += chr(int(byte, 2))

        self.log(f"Unframing frame: {frame} -> Seq: {sequence_number}, Data: '{data}', CRC OK.")
        return sequence_number, data, False

    def process_received_frame(self, sequence_number, data):
        """
        Processes a received frame at the receiver.
        Sends an ACK if the frame is valid and in order.
        """
        if sequence_number is None:
            self.log(f"Received corrupted frame. Discarding.")
            return None

        self.log(f"Received frame {sequence_number}. Expected: {self.next_frame_to_deliver}")

        if sequence_number == self.next_frame_to_deliver:
            self.log(f"Frame {sequence_number} is in order. Delivering '{data}' to Network Layer.")
            self.next_frame_to_deliver += 1
            ack_to_send = sequence_number
            while self.next_frame_to_deliver in self.received_frames:
                buffered_data = self.received_frames.pop(self.next_frame_to_deliver)
                self.log(f"Delivering buffered frame {self.next_frame_to_deliver}: '{buffered_data}' to Network Layer.")
                self.next_frame_to_deliver += 1
            self.log(f"Sending ACK for {ack_to_send}")
            return ack_to_send
        elif sequence_number > self.next_frame_to_deliver:
            self.log(f"Frame {sequence_number} is out of order. Buffering.")
            self.received_frames[sequence_number] = data
            ack_to_send = self.next_frame_to_deliver - 1 if self.next_frame_to_deliver > 0 else None
            if ack_to_send is not None:
                self.log(f"Sending cumulative ACK for {ack_to_send}")
            return ack_to_send
        else:
            self.log(f"Received duplicate frame {sequence_number}. Discarding and re-sending ACK for {sequence_number}.")
            return sequence_number

class DataLinkSimulatorGUI:
    def __init__(self, master):
        self.master = master
        master.title("Data Link Layer Visualization")
        master.geometry("800x700")
        master.configure(bg="#e0f7fa") # Light blue background

        self.sender = None
        self.receiver = None
        self.simulation_data = []
        self.simulation_index = 0
        self.is_running = False

        self.create_widgets()
        self.reset_simulation()

    def create_widgets(self):
        # Title
        title_label = tk.Label(self.master, text="Data Link Layer Simulation", font=("Inter", 20, "bold"), bg="#e0f7fa", fg="#004d40")
        title_label.pack(pady=10)

        # Control Frame
        control_frame = tk.Frame(self.master, bg="#b2ebf2", bd=2, relief="groove", padx=10, pady=10)
        control_frame.pack(pady=10)

        self.data_entry_label = tk.Label(control_frame, text="Data to Send (e.g., Hello):", bg="#b2ebf2", font=("Inter", 10))
        self.data_entry_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.data_entry = tk.Entry(control_frame, width=30, font=("Inter", 10), bd=2, relief="solid")
        self.data_entry.insert(0, "Hello")
        self.data_entry.grid(row=0, column=1, padx=5, pady=5)

        self.start_button = tk.Button(control_frame, text="Start Simulation", command=self.start_simulation, bg="#4CAF50", fg="white", font=("Inter", 10, "bold"), relief="raised", bd=3, cursor="hand2")
        self.start_button.grid(row=0, column=2, padx=10, pady=5)

        self.next_step_button = tk.Button(control_frame, text="Next Step", command=self.next_simulation_step, bg="#2196F3", fg="white", font=("Inter", 10, "bold"), relief="raised", bd=3, cursor="hand2", state=tk.DISABLED)
        self.next_step_button.grid(row=0, column=3, padx=10, pady=5)

        self.reset_button = tk.Button(control_frame, text="Reset", command=self.reset_simulation, bg="#f44336", fg="white", font=("Inter", 10, "bold"), relief="raised", bd=3, cursor="hand2")
        self.reset_button.grid(row=0, column=4, padx=10, pady=5)

        self.introduce_error_var = tk.BooleanVar()
        self.introduce_error_checkbox = tk.Checkbutton(control_frame, text="Introduce Bit Error", variable=self.introduce_error_var, bg="#b2ebf2", font=("Inter", 10))
        self.introduce_error_checkbox.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky="w")

        self.loss_probability_label = tk.Label(control_frame, text="Loss Probability (0.0-1.0):", bg="#b2ebf2", font=("Inter", 10))
        self.loss_probability_label.grid(row=1, column=2, padx=5, pady=5, sticky="w")
        self.loss_probability_entry = tk.Entry(control_frame, width=10, font=("Inter", 10), bd=2, relief="solid")
        self.loss_probability_entry.insert(0, "0.1")
        self.loss_probability_entry.grid(row=1, column=3, padx=5, pady=5)


        # Simulation Status Frame
        status_frame = tk.Frame(self.master, bg="#c8e6c9", bd=2, relief="groove", padx=10, pady=10)
        status_frame.pack(pady=10, fill=tk.X)

        self.sender_status_label = tk.Label(status_frame, text="Sender Status:", font=("Inter", 12, "bold"), bg="#c8e6c9", fg="#1b5e20")
        self.sender_status_label.pack(anchor="w")
        self.sender_buffer_label = tk.Label(status_frame, text="Buffer: []", font=("Inter", 10), bg="#c8e6c9")
        self.sender_buffer_label.pack(anchor="w")
        self.sender_seq_label = tk.Label(status_frame, text="Next Frame to Send: 0", font=("Inter", 10), bg="#c8e6c9")
        self.sender_seq_label.pack(anchor="w")
        self.sender_ack_label = tk.Label(status_frame, text="Expected ACK: 0", font=("Inter", 10), bg="#c8e6c9")
        self.sender_ack_label.pack(anchor="w")

        tk.Frame(status_frame, height=1, bg="#a5d6a7").pack(fill=tk.X, pady=5) # Separator

        self.receiver_status_label = tk.Label(status_frame, text="Receiver Status:", font=("Inter", 12, "bold"), bg="#c8e6c9", fg="#1b5e20")
        self.receiver_status_label.pack(anchor="w")
        self.receiver_expected_label = tk.Label(status_frame, text="Expected Frame to Deliver: 0", font=("Inter", 10), bg="#c8e6c9")
        self.receiver_expected_label.pack(anchor="w")
        self.receiver_buffered_label = tk.Label(status_frame, text="Buffered Frames: {}", font=("Inter", 10), bg="#c8e6c9")
        self.receiver_buffered_label.pack(anchor="w")
        self.receiver_delivered_label = tk.Label(status_frame, text="Delivered Data: ''", font=("Inter", 10), bg="#c8e6c9")
        self.receiver_delivered_label.pack(anchor="w")


        # Log Area
        log_frame = tk.LabelFrame(self.master, text="Simulation Log", font=("Inter", 12, "bold"), bg="#bbdefb", fg="#1a237e", bd=2, relief="groove", padx=5, pady=5)
        log_frame.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

        self.log_text = scrolledtext.ScrolledText(log_frame, width=80, height=15, font=("Inter", 9), wrap=tk.WORD, bd=2, relief="sunken")
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.config(state=tk.DISABLED) # Make it read-only

    def update_status_labels(self):
        """Updates the sender and receiver status labels in the GUI."""
        if self.sender:
            self.sender_buffer_label.config(text=f"Buffer: {self.sender.send_buffer}")
            self.sender_seq_label.config(text=f"Next Frame to Send: {self.sender.next_frame_to_send}")
            self.sender_ack_label.config(text=f"Expected ACK: {self.sender.expected_frame_ack}")
        else: # Clear labels if sender is None (e.g., after reset)
            self.sender_buffer_label.config(text="Buffer: []")
            self.sender_seq_label.config(text="Next Frame to Send: 0")
            self.sender_ack_label.config(text="Expected ACK: 0")


        if self.receiver:
            self.receiver_expected_label.config(text=f"Expected Frame to Deliver: {self.receiver.next_frame_to_deliver}")
            self.receiver_buffered_label.config(text=f"Buffered Frames: {self.receiver.received_frames}")
            # Accumulate delivered data for display
            delivered_data_str = "".join(self.simulation_data[:self.receiver.next_frame_to_deliver])
            self.receiver_delivered_label.config(text=f"Delivered Data: '{delivered_data_str}'")
        else: # Clear labels if receiver is None (e.g., after reset)
            self.receiver_expected_label.config(text="Expected Frame to Deliver: 0")
            self.receiver_buffered_label.config(text="Buffered Frames: {}")
            self.receiver_delivered_label.config(text="Delivered Data: ''")


    def log_channel_message(self, message):
        """Logs channel messages to the GUI's text area."""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"  [Channel] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def simulate_channel_gui(self, frame, introduce_error_flag, loss_prob):
        """
        Simulates a noisy communication channel, updating GUI.
        """
        self.log_channel_message(f"Sending frame: {frame}")
        time.sleep(0.1) # Simulate transmission delay (reduced for faster steps)

        if random.random() < loss_prob:
            self.log_channel_message("!!! Frame lost in transit !!!")
            return None

        if introduce_error_flag and random.random() < 0.3:
            error_index = random.randint(0, len(frame) - 1)
            original_char = frame[error_index]
            corrupted_char = '1' if original_char == '0' else '0'
            corrupted_frame = list(frame)
            corrupted_frame[error_index] = corrupted_char
            corrupted_frame_str = "".join(corrupted_frame)
            self.log_channel_message(f"!!! Bit error introduced at index {error_index} (changed {original_char} to {corrupted_char}) !!!")
            return corrupted_frame_str
        return frame

    def start_simulation(self):
        if self.is_running:
            return

        data_input = self.data_entry.get().strip()
        if not data_input:
            messagebox.showwarning("Input Error", "Please enter data to send.")
            return

        try:
            loss_prob = float(self.loss_probability_entry.get())
            if not (0.0 <= loss_prob <= 1.0):
                raise ValueError
        except ValueError:
            messagebox.showwarning("Input Error", "Loss probability must be a number between 0.0 and 1.0.")
            return

        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)

        self.sender = DataLinkLayerNode("Sender", self.log_text)
        self.receiver = DataLinkLayerNode("Receiver", self.log_text)
        self.simulation_data = list(data_input) # Convert string to list of characters
        self.simulation_index = 0
        self.is_running = True

        self.start_button.config(state=tk.DISABLED)
        self.next_step_button.config(state=tk.NORMAL)
        self.data_entry.config(state=tk.DISABLED)
        self.introduce_error_checkbox.config(state=tk.DISABLED)
        self.loss_probability_entry.config(state=tk.DISABLED)

        # Prepare sender's buffer with all data to be sent
        self.sender.send_buffer.extend(self.simulation_data)
        self.sender.log(f"Sender ready to send data. Buffer: {self.sender.send_buffer}")
        self.update_status_labels()
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, "\n--- Simulation Started ---\n")
        self.log_text.config(state=tk.DISABLED)

    def next_simulation_step(self):
        if not self.is_running:
            return

        introduce_error_flag = self.introduce_error_var.get()
        loss_prob = float(self.loss_probability_entry.get())

        # Check if there are frames left to send or ACKs to receive
        # This condition determines if the simulation should continue.
        # It's simplified for step-by-step; in a real continuous sim,
        # timers would trigger retransmissions.
        can_send_new_frame = (self.sender.next_frame_to_send < len(self.sender.send_buffer) and \
                             self.sender.next_frame_to_send < self.sender.expected_frame_ack + self.sender.window_size)
        
        # In this step-by-step simulation, we prioritize sending if possible,
        # otherwise, we indicate waiting for ACKs.
        if can_send_new_frame:
            data_char = self.sender.send_buffer[self.sender.next_frame_to_send]
            frame_to_send = self.sender.frame_data(data_char, self.sender.next_frame_to_send)
            
            # Simulate channel transmission for the data frame
            received_frame_at_receiver = self.simulate_channel_gui(frame_to_send, introduce_error_flag, loss_prob)

            if received_frame_at_receiver is not None:
                seq_num, data_unframed, is_corrupted = self.receiver.unframe_data(received_frame_at_receiver)
                if not is_corrupted:
                    ack_num_from_receiver = self.receiver.process_received_frame(seq_num, data_unframed)
                    
                    # Simulate channel transmission for the ACK
                    if ack_num_from_receiver is not None:
                        ack_frame = f"ACK-{ack_num_from_receiver}" # Simplified ACK frame
                        self.log_channel_message(f"Sending ACK: {ack_frame}")
                        time.sleep(0.1) # Simulate ACK transmission delay

                        # Assume ACK reaches sender (no loss/corruption for ACK in this simplified model)
                        self.sender.log(f"Received ACK for frame {ack_num_from_receiver}")
                        if ack_num_from_receiver >= self.sender.expected_frame_ack:
                            self.sender.expected_frame_ack = ack_num_from_receiver + 1
                            self.sender.log(f"Sender window base moved to {self.sender.expected_frame_ack}")
                    else:
                        self.sender.log(f"No valid ACK generated by receiver (due to out-of-order or duplicate frame).")
                else:
                    self.sender.log(f"Corrupted data frame received by receiver. Sender will retransmit after timeout (simulated).")
            else:
                self.sender.log(f"Data frame lost in transit. Sender will retransmit after timeout (simulated).")
            
            # Increment next_frame_to_send only if a new frame was actually attempted to be sent
            self.sender.next_frame_to_send += 1

        else:
            # If no new frames can be sent, check if all outstanding frames are acknowledged
            if self.sender.expected_frame_ack < len(self.sender.send_buffer):
                self.sender.log(f"No new frames to send within window. Waiting for ACKs. "
                                f"Window: [{self.sender.expected_frame_ack}, {self.sender.expected_frame_ack + self.sender.window_size - 1}]")
                # In a real protocol, a timeout would retransmit unacknowledged frames here.
                # For this step-by-step GUI, the user clicks "Next Step" to advance.
            else:
                self.sender.log(f"All data sent and acknowledged.")
                self.end_simulation()
                return # Exit early if simulation finished

        self.update_status_labels()

        # Check for global completion after each step
        if self.sender.expected_frame_ack == len(self.sender.send_buffer) and \
           self.receiver.next_frame_to_deliver == len(self.simulation_data):
            self.end_simulation()


    def end_simulation(self):
        self.is_running = False
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, "\n--- Simulation Finished ---\n")
        self.log_text.config(state=tk.DISABLED)
        self.next_step_button.config(state=tk.DISABLED)
        self.start_button.config(state=tk.NORMAL) # Re-enable start button for new simulation
        messagebox.showinfo("Simulation Complete", "All data has been sent and acknowledged.")


    def reset_simulation(self):
        self.is_running = False
        self.sender = None
        self.receiver = None
        self.simulation_data = []
        self.simulation_index = 0

        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.insert(tk.END, "Simulation ready. Enter data and click 'Start Simulation'.\n")
        self.log_text.config(state=tk.DISABLED)

        self.data_entry.config(state=tk.NORMAL)
        self.data_entry.delete(0, tk.END)
        self.data_entry.insert(0, "Hello")
        self.introduce_error_checkbox.config(state=tk.NORMAL)
        self.loss_probability_entry.config(state=tk.NORMAL)
        self.loss_probability_entry.delete(0, tk.END)
        self.loss_probability_entry.insert(0, "0.1")

        self.start_button.config(state=tk.NORMAL)
        self.next_step_button.config(state=tk.DISABLED)
        self.update_status_labels() # Clear status labels

def main():
    root = tk.Tk()
    app = DataLinkSimulatorGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()