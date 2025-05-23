from ultralytics import YOLO

yaml_path = "dataset.yaml"
model = YOLO("yolov10n.pt")

model.train(
    data=yaml_path,
    epochs=100,
    imgsz=640,
    batch=16,
    project="runs",
    name="yolov10_train"
)

results = model.predict(source="dataset/images/val", save=True, conf=0.25)

if True:
    results = model.predict(source="scacchiera_personale/laterale_set_legno.png", save=True, conf=0.25)
    results = model.predict(source="scacchiera_personale/laterale_set_plastica.png", save=True, conf=0.25)
    results = model.predict(source="scacchiera_personale/alto_set_plastica.png", save=True, conf=0.25)
    results = model.predict(source="scacchiera_personale/frontale_set_legno.png", save=True, conf=0.25)

