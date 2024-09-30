# This is the main file for a Chinese Video Game Translator
# It works by taking a screenshot and extracting the text from the screenshot
# It then takes the extracted text and sends it to google translator for translating
# It also has the capabilities to aid in the annotation of text

import tkinter
import time
import csv
import os
import joblib

import configparser

from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from tkinter import ttk
from tkinter import filedialog
from PIL import ImageTk, Image
from googletrans import Translator

from azure.cognitiveservices.vision.computervision import ComputerVisionClient
from azure.cognitiveservices.vision.computervision.models import OperationStatusCodes
from azure.cognitiveservices.vision.computervision.models import VisualFeatureTypes
from msrest.authentication import CognitiveServicesCredentials

config = configparser.ConfigParser()
config.read("conf.ini")

endpoint = "https://gametranslationvision.cognitiveservices.azure.com/"

subscriptionKey = config["External Services"]["AzureOCRKey"]

# Load in any screenhots that have already been proccessed
screenshotsToBeProcessed = []
currentImageID = 0
if os.path.exists("screenshotsFile.csv"):
    with open("screenshotsFile.csv", "r", newline="") as screenshotsFile:
        reader = csv.reader(screenshotsFile)
        data = list(reader)
        if len(data) > 0:
            currentImageID = int(data[-1][1]) + 1
            for line in data:
                screenshotsToBeProcessed.append(line[0])

# Azure OCR ComputerVisionClient
computervision_client = ComputerVisionClient(
    endpoint, CognitiveServicesCredentials(subscriptionKey)
)

# Google translate translator
translator = Translator()

model = None

def makeModel():
    global model
    with open(
        filedialog.askopenfilename(), newline="", mode="r", encoding="utf-8"
    ) as dataFile:
        reader = csv.reader(dataFile)
        dataArray = []
        answersArray = []
        data = list(reader)
        for line in data:
            data = line[0].split()
            newData = []
            # Get rid of the brackets and commans
            newData.append(float(data[0][1:-1]))
            newData.append(float(data[1][:-1]))
            newData.append(float(data[2][:-1]))
            newData.append(float(data[3][:-1]))
            dataArray.append(newData[0:3])
            answersArray.append(newData[3])
    xTrain, xTest, yTrain, yTest = train_test_split(
        dataArray, answersArray, test_size=0.2, random_state=42
    )
    model = LogisticRegression()
    model.fit(xTrain, yTrain)
    yPred = model.predict(xTest)

    accuracy = accuracy_score(yTest, yPred)
    print(f"Accuracy: {accuracy}")

    joblib.dump(model, "modelV1.pk1")


def loadModel():
    global model
    model = joblib.load(filedialog.askopenfilename())


def makePrediction():
    global model
    currentItemId = annotationTreeView.focus()
    if currentItemId == "" or model is None:
        print("Noned out")
        return
    currentAnnotation = dataToBeAnnotated[int(currentItemId[1:], 16) - 1]
    prediction = model.predict(
        [[len(currentAnnotation[3]), currentAnnotation[0], currentAnnotation[1]]]
    )
    print("Prediction Made")
    predictionLabelString.set(str(prediction))


# This returns just the text from the translater.
# Although this funciton is not sctrictly needed
def getTranslationInformation(inText):
    return translator.translate(inText).text


# This is the annotated information and should be written and read from a file
# The data should be layed out like this [[textlength, pos.x, pos.y, isDialogueSpeaker], text, translatedText, ID]
annotatedInformation = []

# Annotates information
def createAnnotation():
    # Get current selection
    currentItemid = annotationTreeView.focus()
    if currentItemid == "":
        return
    # Getting the index from the currentItemid like this feels like a hack
    # There is an I at the begining of the currentItemid for use in the Treeview
    # Here the I is stripped and that is used to get the
    currentAnnotation = dataToBeAnnotated[int(currentItemid[1:], 16) - 1]
    # We have the annotation we need to put in in it's final annotated form and we need to make a checkbox and get the state of that we can also make it so that when it's chose
    annotatedInformation.append(
        [
            [
                len(currentAnnotation[3]),
                currentAnnotation[0],
                currentAnnotation[1],
                isDialogueValue.get(),
            ],
            currentAnnotation[2],
            currentAnnotation[3],
            currentAnnotation[4],
        ]
    )

    annotationTreeView.delete(currentItemid)
    dataToBeAnnotated.remove(currentItemid)


# Write anootation to file bound to a button
def writeAnnotations():
    with open(
        "AnnotationData.csv", "w", newline="", encoding="utf-8"
    ) as annotationDataFile:
        writer = csv.writer(annotationDataFile)
        writer.writerows(annotatedInformation)


# Sends information to the OCR service and gets the proper information back
def getOCRInformation(filename):
    with open(filename, "rb") as binaryImage:
        try:
            read_response = computervision_client.read_in_stream(binaryImage, raw=True)
        except:
            print("Tried and failed")
            time.sleep(60)
            return getOCRInformation(filename)

        read_operation_location = read_response.headers["Operation-Location"]
        operation_id = read_operation_location.split("/")[-1]
        while True:
            read_result = computervision_client.get_read_result(operation_id)
            if read_result.status not in ["notStarted", "running"]:
                break
            time.sleep(1)

    if read_result.status == OperationStatusCodes.succeeded:
        return read_result

    return 0


def addFilesToAnnotationQueue():
    screenshotsToBeProcessed.extend(filedialog.askopenfilenames())
    if len(screenshotsToBeProcessed) > 0:
        processScreenShots()
        annotationTreeView.delete(*annotationTreeView.get_children())
        for i in dataToBeAnnotated:
            annotationTreeView.insert("", "end", text=i[3], tags=i[4])


def itemSelected(inname):
    print(inname)
    currentItemId = annotationTreeView.focus()
    currentItem = annotationTreeView.item(currentItemId)
    localImage = Image.open(screenshotsToBeProcessed[currentItem["tags"][0]])
    global testImage2

    testImage2 = ImageTk.PhotoImage(localImage.resize((640, 360)))
    ocrLabel.configure(image=testImage2)


# This is an array of information that needs to annotated the elements should be [textpos.x,textpox.y, text,translatedtext, imageID]
dataToBeAnnotated = []


# Modify this to work with a progress bar
def processScreenShots():
    global currentImageID
    for idx, file in enumerate(screenshotsToBeProcessed):
        print("Processing " + file)
        # This helps stop images from being processed twice
        if idx < currentImageID:
            continue

        if idx % 8 == 0 and idx != 0:
            print("Waiting for a minute")
            time.sleep(60)

        # Add filename and id to file
        with open("screenshotsFile.csv", "a", newline="") as screenshotsFile:
            screenshotsWriter = csv.writer(screenshotsFile)
            screenshotsWriter.writerow([file, str(currentImageID)])

        readResult = getOCRInformation(file)
        if readResult != 0:
            for textResult in readResult.analyze_result.read_results:
                for read in textResult.lines:
                    localBoundingBox = read.bounding_box
                    # while True:
                    # try:
                    translatedText = getTranslationInformation(read.text)
                    # except:
                    # print("Failed to translate")
                    # continue
                    # break
                    dataToBeAnnotated.append(
                        [
                            read.bounding_box[2] - read.bounding_box[0],
                            read.bounding_box[7] - read.bounding_box[3],
                            read.text,
                            translatedText,
                            currentImageID,
                        ]
                    )
        else:
            print("READ RESULT FAILED " + file)
        currentImageID += 1


guiRoot = tkinter.Tk()
guiRoot.rowconfigure(0, weight=1)
guiRoot.columnconfigure(0, weight=1)

mainframe = ttk.Frame(guiRoot)
mainframe.grid(column=0, row=0, sticky=tkinter.NSEW)
mainframe.grid_columnconfigure(1, weight=1)

menuBar = tkinter.Menu()

guiRoot.config(menu=menuBar)


fileMenu = tkinter.Menu(menuBar, tearoff=False)
menuBar.add_cascade(menu=fileMenu, label="Model")


fileMenu.add_command(label="Make Model", command=makeModel)
fileMenu.add_command(label="Load Model", command=loadModel)

ocrLabelString = tkinter.StringVar()
ocrLabelString.set("Test string OCR")
predictionLabelString = tkinter.StringVar()
predictionLabelString.set("Predicition")
# OCR
testImage2 = ImageTk.PhotoImage(Image.open("storytime.png"))
ocrLabel = tkinter.Label(mainframe, textvariable=ocrLabelString, image=testImage2)
ocrLabel.grid(column=0, row=0, sticky=tkinter.W)

secondFrame = ttk.Frame(mainframe)
secondFrame.grid(column=1, row=0, sticky=tkinter.NSEW)

ttk.Button(secondFrame, text="Get Screenshots", command=addFilesToAnnotationQueue).grid(
    column=0, row=0, sticky=tkinter.W
)
# Annotation
annotationFrame = ttk.Frame(secondFrame)
annotationFrame.grid(column=0, row=1, sticky=tkinter.NSEW)

isDialogueValue = tkinter.IntVar()
isDialogueSpeakerCheckbox = ttk.Checkbutton(
    annotationFrame, text="Dialogue Speaker", variable=isDialogueValue
)
isDialogueSpeakerCheckbox.grid(column=0, row=0, sticky=tkinter.NSEW)

ttk.Button(annotationFrame, text="Confirm", command=createAnnotation).grid(
    column=0, row=1, sticky=tkinter.NSEW
)

ttk.Button(annotationFrame, text="Save", command=writeAnnotations).grid(
    column=0, row=2, sticky=tkinter.NSEW
)

ttk.Button(annotationFrame, text="Predict", command=makePrediction).grid(
    column=0, row=3, sticky=tkinter.NSEW
)

predicitonLabel = tkinter.Label(annotationFrame, textvariable=predictionLabelString)
predicitonLabel.grid(column=0, row=4)
annotationScrollBar = ttk.Scrollbar(guiRoot)
annotationTreeView = ttk.Treeview(
    annotationFrame, yscrollcommand=annotationScrollBar.set, show="tree"
)
annotationTreeView.grid(column=1, row=2, sticky=tkinter.NSEW, columnspan=2)
annotationTreeView.bind("<ButtonRelease-1>", func=itemSelected)
guiRoot.mainloop()
