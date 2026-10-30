insert into floors (id, code, name) values (2, '2', '2F'), (4, '4', '4F');
insert into rooms (id, floor_id, code, name) values (1, 2, 'R1', '제1열람실'), (2,4,'R2', '제2열람실'), (3,4,'HOLMZ', '노상일 HOLMZ'),(4,4,'FOCUS', '집중열람실');
insert into seats (id, room_id, number) values (0,1,'1'),(1,1,'2'),(2,2,'1'),(3,2,'2'),(4,3,'1'),(5,3,'2'),(6,4,'1'),(7,4,'2');
