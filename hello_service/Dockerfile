# Gunakan image python sebagai base image
FROM python:3.11.3

# Set working directory
WORKDIR /app

# Copy file requirements.txt ke dalam container
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy seluruh kode ke dalam container
COPY . .

# Expose port yang akan digunakan oleh aplikasi Flask
EXPOSE 5001

# Jalankan aplikasi Flask
CMD ["python", "app.py"]
